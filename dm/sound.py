"""Звук из лампов DS* через winsound (один канал, с приоритетами)."""
import os
import struct
import time

IS_WIN = os.name == 'nt'


def dmx_to_wav(data):
    """Формат DOOM: u16 тип(3), u16 частота, u32 отсчётов, дальше 8-битный PCM."""
    if len(data) < 8:
        return None, 0.0
    fmt, rate, count = struct.unpack_from('<HHI', data, 0)
    if fmt != 3 or rate <= 0:
        return None, 0.0
    pcm = data[8:8 + count]
    if len(pcm) < 16:
        return None, 0.0
    pcm = pcm[16:-16] if len(pcm) > 32 else pcm      # DOOM дублирует крайние отсчёты
    n = len(pcm)
    hdr = b'RIFF' + struct.pack('<I', 36 + n) + b'WAVEfmt ' + \
        struct.pack('<IHHIIHH', 16, 1, 1, rate, rate, 1, 8) + \
        b'data' + struct.pack('<I', n)
    return hdr + pcm, n / float(rate)


class Sound:
    def __init__(self, wad, enabled=True):
        self.wad = wad
        self.enabled = enabled and IS_WIN
        self.cache = {}
        self.busy_until = 0.0
        self.busy_prio = 0
        self._ws = None
        if self.enabled:
            try:
                import winsound
                self._ws = winsound
            except Exception:
                self.enabled = False

    def _get(self, name):
        got = self.cache.get(name)
        if got is None:
            data = self.wad.read(name)
            got = dmx_to_wav(data) if data else (None, 0.0)
            self.cache[name] = got
        return got

    def play(self, name, prio=1):
        """prio: 3 — оружие/взрыв, 2 — боль/смерть, 1 — прочее."""
        if not self.enabled or not name:
            return
        now = time.time()
        if now < self.busy_until and prio < self.busy_prio:
            return
        wav, dur = self._get(name)
        if not wav:
            return
        try:
            self._ws.PlaySound(wav, self._ws.SND_MEMORY | self._ws.SND_ASYNC |
                               self._ws.SND_NODEFAULT)
        except Exception:
            self.enabled = False
            return
        self.busy_until = now + min(dur, 1.2)
        self.busy_prio = prio

    def stop(self):
        if self.enabled and self._ws:
            try:
                self._ws.PlaySound(None, self._ws.SND_PURGE)
            except Exception:
                pass
