"""Звук и музыка.

Звук: лампы DS* распаковываются в 16-битный PCM и мешаются своим микшером —
на Windows поток идёт прямо в waveOut через ctypes, так что каналов много и
выстрел не обрывает рычание монстра. На других системах — запуск проигрывателя
(paplay/aplay/afplay) на каждый звук.

Музыка: лампы D_* бывают в MIDI (Freedoom) и в MUS (оригинальный DOOM) —
второй конвертируется в MIDI и играется системным синтезатором.
"""
import os
import struct
import subprocess
import shutil
import sys
import tempfile
import threading
import time
from array import array

from .mus import mus_to_midi, is_mus

IS_WIN = os.name == 'nt'
RATE = 22050
BUF_SAMPLES = 1024
NBUF = 4
MAX_VOICES = 8


# ---------------------------------------------------------------- лампы DS*
def dmx_decode(data, rate=RATE):
    """Формат DOOM: u16 тип(3), u16 частота, u32 отсчётов, дальше 8-битный PCM.
    -> array('h') с частотой rate."""
    if len(data) < 8:
        return None
    fmt, src_rate, count = struct.unpack_from('<HHI', data, 0)
    if fmt != 3 or src_rate <= 0:
        return None
    pcm = data[8:8 + count]
    if len(pcm) > 32:
        pcm = pcm[16:-16]            # DOOM дублирует крайние отсчёты
    if not pcm:
        return None
    out = array('h', bytes(0))
    if src_rate == rate:
        out.extend(((b - 128) << 7) for b in pcm)
    else:
        n = int(len(pcm) * rate / src_rate)
        step = len(pcm) / float(n) if n else 1.0
        out.extend(((pcm[int(i * step)] - 128) << 7) for i in range(n))
    return out


def wav_bytes(samples, rate=RATE):
    raw = samples.tobytes()
    return (b'RIFF' + struct.pack('<I', 36 + len(raw)) + b'WAVEfmt ' +
            struct.pack('<IHHIIHH', 16, 1, 1, rate, rate * 2, 2, 16) +
            b'data' + struct.pack('<I', len(raw)) + raw)


# ---------------------------------------------------------------- микшер
class WaveOut:
    """Многоканальный вывод через winmm.waveOut. Смешивание — в своём потоке."""

    WHDR_DONE = 1

    def __init__(self):
        import ctypes
        self.ct = ctypes
        self.winmm = ctypes.windll.winmm

        class WAVEFORMATEX(ctypes.Structure):
            _fields_ = [('wFormatTag', ctypes.c_uint16),
                        ('nChannels', ctypes.c_uint16),
                        ('nSamplesPerSec', ctypes.c_uint32),
                        ('nAvgBytesPerSec', ctypes.c_uint32),
                        ('nBlockAlign', ctypes.c_uint16),
                        ('wBitsPerSample', ctypes.c_uint16),
                        ('cbSize', ctypes.c_uint16)]

        class WAVEHDR(ctypes.Structure):
            pass

        WAVEHDR._fields_ = [('lpData', ctypes.c_void_p),
                            ('dwBufferLength', ctypes.c_uint32),
                            ('dwBytesRecorded', ctypes.c_uint32),
                            ('dwUser', ctypes.c_void_p),
                            ('dwFlags', ctypes.c_uint32),
                            ('dwLoops', ctypes.c_uint32),
                            ('lpNext', ctypes.c_void_p),
                            ('reserved', ctypes.c_void_p)]
        self.WAVEHDR = WAVEHDR

        wfx = WAVEFORMATEX(1, 1, RATE, RATE * 2, 2, 16, 0)
        self.h = ctypes.c_void_p()
        rc = self.winmm.waveOutOpen(ctypes.byref(self.h), 0xFFFFFFFF,
                                    ctypes.byref(wfx), 0, 0, 0)
        if rc != 0:
            raise OSError('waveOutOpen -> %d' % rc)

        nbytes = BUF_SAMPLES * 2
        self.bufs = []
        for _ in range(NBUF):
            mem = ctypes.create_string_buffer(nbytes)
            hdr = WAVEHDR()
            hdr.lpData = ctypes.cast(mem, ctypes.c_void_p)
            hdr.dwBufferLength = nbytes
            hdr.dwFlags = 0
            self.winmm.waveOutPrepareHeader(self.h, ctypes.byref(hdr),
                                            ctypes.sizeof(hdr))
            hdr.dwFlags |= self.WHDR_DONE          # свободен
            self.bufs.append((hdr, mem))

        self.voices = []                            # [samples, pos, prio]
        self.lock = threading.Lock()
        self.silence = array('h', [0]) * BUF_SAMPLES
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def add(self, samples, prio):
        with self.lock:
            if len(self.voices) >= MAX_VOICES:
                worst = min(range(len(self.voices)),
                            key=lambda i: self.voices[i][2])
                if self.voices[worst][2] > prio:
                    return
                self.voices.pop(worst)
            self.voices.append([samples, 0, prio])

    def _mix(self):
        with self.lock:
            voices = self.voices
            if not voices:
                return None
            out = array('h', self.silence)
            done = []
            for v in voices:
                s, pos, _ = v
                n = len(s) - pos
                if n > BUF_SAMPLES:
                    n = BUF_SAMPLES
                for i in range(n):
                    m = out[i] + s[pos + i]
                    if m > 32767:
                        m = 32767
                    elif m < -32768:
                        m = -32768
                    out[i] = m
                v[1] = pos + n
                if v[1] >= len(s):
                    done.append(v)
            for v in done:
                voices.remove(v)
            return out

    def _loop(self):
        ct = self.ct
        while self.running:
            mixed = self._mix()
            if mixed is None:
                time.sleep(0.01)
                continue
            queued = False
            for hdr, mem in self.bufs:
                if hdr.dwFlags & self.WHDR_DONE:
                    ct.memmove(mem, mixed.tobytes(), BUF_SAMPLES * 2)
                    hdr.dwFlags &= ~self.WHDR_DONE
                    self.winmm.waveOutWrite(self.h, ct.byref(hdr),
                                            ct.sizeof(hdr))
                    queued = True
                    break
            if not queued:
                time.sleep(0.005)

    def close(self):
        self.running = False
        try:
            self.thread.join(timeout=0.5)
        except Exception:
            pass
        try:
            self.winmm.waveOutReset(self.h)
            for hdr, _ in self.bufs:
                self.winmm.waveOutUnprepareHeader(self.h, self.ct.byref(hdr),
                                                  self.ct.sizeof(hdr))
            self.winmm.waveOutClose(self.h)
        except Exception:
            pass


class CmdPlayer:
    """Запасной вывод: системный проигрыватель на каждый звук (Linux/macOS)."""

    def __init__(self):
        self.cmd = None
        for name, args in (('paplay', []), ('aplay', ['-q']), ('afplay', [])):
            if shutil.which(name):
                self.cmd = [name] + args
                break
        if self.cmd is None:
            raise OSError('нет ни paplay, ни aplay, ни afplay')
        self.dir = tempfile.mkdtemp(prefix='tdoom-snd-')
        self.files = {}
        self.procs = []

    def add_file(self, key, samples):
        path = os.path.join(self.dir, '%s.wav' % key)
        with open(path, 'wb') as f:
            f.write(wav_bytes(samples))
        self.files[key] = path
        return path

    def play_file(self, path):
        self.procs = [p for p in self.procs if p.poll() is None]
        if len(self.procs) >= MAX_VOICES:
            return
        try:
            self.procs.append(subprocess.Popen(
                self.cmd + [path], stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL))
        except Exception:
            pass

    def close(self):
        for p in self.procs:
            try:
                p.terminate()
            except Exception:
                pass
        shutil.rmtree(self.dir, ignore_errors=True)


# ---------------------------------------------------------------- фасад
class Sound:
    def __init__(self, wad, enabled=True):
        self.wad = wad
        self.cache = {}
        self.backend = None
        self.kind = 'нет'
        if enabled:
            if IS_WIN:
                try:
                    self.backend = WaveOut()
                    self.kind = 'waveOut (микшер)'
                except Exception:
                    self.backend = None
            if self.backend is None:
                try:
                    self.backend = CmdPlayer()
                    self.kind = ' '.join(self.backend.cmd)
                except Exception:
                    self.backend = None
        self.enabled = self.backend is not None

    def _get(self, name):
        got = self.cache.get(name)
        if got is None:
            data = self.wad.read(name)
            samples = dmx_decode(data) if data else None
            if samples is not None and isinstance(self.backend, CmdPlayer):
                got = self.backend.add_file(name, samples)
            else:
                got = samples
            self.cache[name] = got if got is not None else False
        return got or None

    def play(self, name, prio=1):
        """prio: 3 — оружие и взрывы, 2 — боль и смерть, 1 — прочее."""
        if not self.enabled or not name:
            return
        got = self._get(name)
        if got is None:
            return
        if isinstance(self.backend, CmdPlayer):
            self.backend.play_file(got)
        else:
            self.backend.add(got, prio)

    def stop(self):
        if self.backend is not None:
            self.backend.close()
            self.backend = None
            self.enabled = False


# ---------------------------------------------------------------- музыка
class Music:
    """Лампы D_*: MIDI играется системным синтезатором, MUS сначала конвертируется."""

    def __init__(self, wad, enabled=True):
        self.wad = wad
        self.enabled = enabled
        self.dir = None
        self.alias = 'tdoommus'
        self.playing = False
        self.path = None
        self.proc = None
        self.check_t = 0.0
        self.kind = 'нет'
        self._mci = None
        if not enabled:
            return
        if IS_WIN:
            try:
                import ctypes
                self._mci = ctypes.windll.winmm.mciSendStringW
                self.kind = 'MCI (системный синтезатор)'
            except Exception:
                self.enabled = False
        else:
            for name in ('fluidsynth', 'timidity', 'wildmidi'):
                if shutil.which(name):
                    self.kind = name
                    break
            else:
                self.enabled = False
        if self.enabled:
            self.dir = tempfile.mkdtemp(prefix='tdoom-mus-')

    def lump_for(self, mapname):
        for cand in ('D_' + mapname, 'D_' + mapname.replace('MAP', 'RUNNI')):
            if self.wad.has(cand):
                return cand
        return None

    def play_map(self, mapname):
        if not self.enabled:
            return False
        name = self.lump_for(mapname)
        if not name:
            return False
        data = self.wad.read(name)
        if data is None:
            return False
        if is_mus(data):
            data = mus_to_midi(data)
            if data is None:
                return False
        elif data[:4] != b'MThd':
            return False
        self.stop()
        path = os.path.join(self.dir, '%s.mid' % name)
        with open(path, 'wb') as f:
            f.write(data)
        self.path = path
        return self._start()

    def _start(self):
        if IS_WIN:
            self._cmd('open "%s" type sequencer alias %s' % (self.path, self.alias))
            self._cmd('play %s' % self.alias)
        else:
            cmd = {'fluidsynth': ['fluidsynth', '-a', 'alsa', '-i', self.path],
                   'timidity': ['timidity', '-quiet', self.path],
                   'wildmidi': ['wildmidi', '-n', self.path]}.get(self.kind)
            if not cmd:
                return False
            try:
                self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                             stderr=subprocess.DEVNULL)
            except Exception:
                return False
        self.playing = True
        return True

    def _cmd(self, s):
        if self._mci is None:
            return ''
        import ctypes
        buf = ctypes.create_unicode_buffer(256)
        self._mci(s, buf, 255, None)
        return buf.value

    def update(self, dt):
        """Зациклить трек, когда он доиграл."""
        if not self.playing:
            return
        self.check_t += dt
        if self.check_t < 1.0:
            return
        self.check_t = 0.0
        if IS_WIN:
            if self._cmd('status %s mode' % self.alias).strip() == 'stopped':
                self._cmd('seek %s to start' % self.alias)
                self._cmd('play %s' % self.alias)
        elif self.proc is not None and self.proc.poll() is not None:
            self._start()

    def stop(self):
        if IS_WIN and self.playing:
            self._cmd('stop %s' % self.alias)
            self._cmd('close %s' % self.alias)
        if self.proc is not None:
            try:
                self.proc.terminate()
            except Exception:
                pass
            self.proc = None
        self.playing = False

    def close(self):
        self.stop()
        if self.dir:
            shutil.rmtree(self.dir, ignore_errors=True)
            self.dir = None
