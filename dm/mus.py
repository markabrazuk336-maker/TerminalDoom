"""Преобразование лампа MUS в стандартный MIDI-файл.

MUS — урезанный формат id Software: события идут в тиках по 140 Гц, канал 15
ударный. Чтобы не возиться с темпом, ставим 140 тиков на четверть и темп в одну
секунду на четверть — тогда один тик MIDI равен одному тику MUS.
"""
import struct

TICKS = 140                      # тиков в секунду в MUS
TEMPO = 1000000                  # микросекунд на четверть -> 140 тиков/с

# контроллеры MUS -> контроллеры MIDI
CTRL = {0: 0, 1: 0, 2: 1, 3: 7, 4: 10, 5: 11, 6: 91, 7: 93, 8: 64, 9: 67}
# системные события MUS 10..14 -> контроллеры MIDI
SYS = {10: 120, 11: 123, 12: 126, 13: 127, 14: 121}


def is_mus(data):
    return bool(data) and len(data) > 16 and data[:4] == b'MUS\x1a'


def _varlen(v):
    out = bytearray()
    out.append(v & 0x7F)
    v >>= 7
    while v:
        out.append((v & 0x7F) | 0x80)
        v >>= 7
    out.reverse()
    return bytes(out)


def mus_to_midi(data):
    """-> байты MIDI-файла (формат 0) либо None, если это не MUS."""
    if not is_mus(data):
        return None
    score_len, score_start, channels = struct.unpack_from('<HHH', data, 4)
    pos = score_start
    end = min(len(data), score_start + score_len) if score_len else len(data)

    track = bytearray()
    track += b'\x00\xff\x51\x03' + struct.pack('>I', TEMPO)[1:]
    delay = 0
    last_vol = [100] * 16
    playing = True
    while pos < end and playing:
        ev = data[pos]
        pos += 1
        etype = (ev >> 4) & 7
        chan = ev & 15
        midi_chan = 9 if chan == 15 else (chan if chan < 9 else chan + 1)
        if midi_chan > 15:
            midi_chan = 15
        msg = None
        if etype == 0:                                  # отпустить ноту
            note = data[pos] & 0x7F
            pos += 1
            msg = bytes((0x80 | midi_chan, note, 64))
        elif etype == 1:                                # взять ноту
            b = data[pos]
            pos += 1
            note = b & 0x7F
            if b & 0x80:
                last_vol[chan] = data[pos] & 0x7F
                pos += 1
            msg = bytes((0x90 | midi_chan, note, last_vol[chan]))
        elif etype == 2:                                # изгиб тона
            b = data[pos]
            pos += 1
            bend = int(b * 64)
            msg = bytes((0xE0 | midi_chan, bend & 0x7F, (bend >> 7) & 0x7F))
        elif etype == 3:                                # системное событие
            b = data[pos] & 0x7F
            pos += 1
            cc = SYS.get(b)
            if cc is not None:
                msg = bytes((0xB0 | midi_chan, cc, 0))
        elif etype == 4:                                # контроллер
            c = data[pos] & 0x7F
            v = data[pos + 1] & 0x7F
            pos += 2
            if c == 0:
                msg = bytes((0xC0 | midi_chan, v))      # смена инструмента
            else:
                cc = CTRL.get(c)
                if cc is not None:
                    msg = bytes((0xB0 | midi_chan, cc, v))
        elif etype == 5:                                # конец такта
            pass
        elif etype == 6:                                # конец партитуры
            playing = False
        else:                                           # 7 — не используется
            pos += 1

        if msg:
            track += _varlen(delay) + msg
            delay = 0
        if ev & 0x80:                                   # дальше пауза
            d = 0
            while pos < end:
                b = data[pos]
                pos += 1
                d = (d << 7) | (b & 0x7F)
                if not (b & 0x80):
                    break
            delay += d

    track += _varlen(delay) + b'\xff\x2f\x00'           # конец дорожки
    head = b'MThd' + struct.pack('>IHHH', 6, 0, 1, TICKS)
    return head + b'MTrk' + struct.pack('>I', len(track)) + bytes(track)


def midi_summary(midi):
    """Разбор обратно — для проверки, что файл собран корректно."""
    if not midi or midi[:4] != b'MThd':
        return None
    ln, fmt, ntrk, div = struct.unpack_from('>IHHH', midi, 4)
    p = 8 + ln
    events = 0
    notes = 0
    ticks = 0
    while p < len(midi) and midi[p:p + 4] == b'MTrk':
        tlen = struct.unpack_from('>I', midi, p + 4)[0]
        q = p + 8
        tend = q + tlen
        status = 0
        while q < tend:
            d = 0
            while q < tend:
                b = midi[q]
                q += 1
                d = (d << 7) | (b & 0x7F)
                if not (b & 0x80):
                    break
            ticks += d
            if q >= tend:
                break
            b = midi[q]
            if b & 0x80:
                status = b
                q += 1
            if status == 0xFF:
                meta = midi[q]
                q += 1
                mlen = 0
                while q < tend:
                    c = midi[q]
                    q += 1
                    mlen = (mlen << 7) | (c & 0x7F)
                    if not (c & 0x80):
                        break
                q += mlen
                if meta == 0x2F:
                    break
            elif status & 0xF0 in (0xC0, 0xD0):
                q += 1
            else:
                if status & 0xF0 == 0x90:
                    notes += 1
                q += 2
            events += 1
        p = tend
    return dict(format=fmt, tracks=ntrk, division=div, events=events,
                notes=notes, seconds=ticks / float(div or 1))
