"""Терминал: VT-режим, полукадровый framebuffer (символ = 2 пикселя), опрос клавиш."""
import os
import sys
import shutil
import time
from array import array

IS_WIN = os.name == 'nt'
HALF = '▀'  # верхний полублок: fg = верхний пиксель, bg = нижний


# ---------------------------------------------------------------- консоль
class Console:
    def __init__(self):
        self._old_mode = None
        self.cols, self.rows = self.size()

    @staticmethod
    def size():
        s = shutil.get_terminal_size((100, 30))
        return s.columns, s.lines

    def setup(self):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
        if IS_WIN:
            import ctypes
            k = ctypes.windll.kernel32
            h = k.GetStdHandle(-11)
            mode = ctypes.c_uint32()
            if k.GetConsoleMode(h, ctypes.byref(mode)):
                self._old_mode = mode.value
                k.SetConsoleMode(h, mode.value | 0x0004)  # VIRTUAL_TERMINAL_PROCESSING
        sys.stdout.write('\x1b[?1049h\x1b[?25l\x1b[2J')
        sys.stdout.flush()

    def restore(self):
        sys.stdout.write('\x1b[0m\x1b[?25h\x1b[?1049l')
        sys.stdout.flush()
        if IS_WIN and self._old_mode is not None:
            import ctypes
            k = ctypes.windll.kernel32
            k.SetConsoleMode(k.GetStdHandle(-11), self._old_mode)


# ---------------------------------------------------------------- кадр
class Frame:
    """Пиксельный буфер. Ширина = колонки терминала, высота = строки * 2."""

    def __init__(self, cols, rows):
        self.cols = cols
        self.rows = rows
        self.w = cols
        self.h = rows * 2
        n = self.w * self.h
        self.pix = array('i', [0]) * n
        self._blank = array('i', [0]) * n
        self.text = {}

    def clear(self, color=0):
        if color != self._blank[0]:
            self._blank = array('i', [color]) * (self.w * self.h)
        self.pix[:] = self._blank
        self.text.clear()

    def put(self, row, col, s, color=0xFFFFFF):
        """Текстовый оверлей поверх пикселей."""
        if not (0 <= row < self.rows):
            return
        for i, ch in enumerate(s):
            c = col + i
            if 0 <= c < self.cols:
                self.text[(row, c)] = (ch, color)

    def rect(self, x0, y0, x1, y1, color):
        w, h = self.w, self.h
        x0 = max(0, x0)
        y0 = max(0, y0)
        x1 = min(w, x1)
        y1 = min(h, y1)
        pix = self.pix
        for y in range(y0, y1):
            o = y * w
            for x in range(x0, x1):
                pix[o + x] = color

    def flush(self):
        w = self.w
        pix = self.pix
        text = self.text
        out = ['\x1b[H']
        app = out.append
        lfg = -1
        lbg = -1
        for row in range(self.rows):
            o1 = row * 2 * w
            o2 = o1 + w
            app('\x1b[%d;1H' % (row + 1))
            for x in range(w):
                t = pix[o1 + x]
                b = pix[o2 + x]
                cell = text.get((row, x))
                if cell is None:
                    if t == b:
                        if b != lbg:
                            app('\x1b[48;2;%d;%d;%dm' % ((b >> 16) & 255, (b >> 8) & 255, b & 255))
                            lbg = b
                        app(' ')
                    else:
                        if t != lfg:
                            app('\x1b[38;2;%d;%d;%dm' % ((t >> 16) & 255, (t >> 8) & 255, t & 255))
                            lfg = t
                        if b != lbg:
                            app('\x1b[48;2;%d;%d;%dm' % ((b >> 16) & 255, (b >> 8) & 255, b & 255))
                            lbg = b
                        app(HALF)
                else:
                    ch, fg = cell
                    bg = (((t >> 17) & 0x7F) << 16) | (((t >> 9) & 0x7F) << 8) | ((t >> 1) & 0x7F)
                    if fg != lfg:
                        app('\x1b[38;2;%d;%d;%dm' % ((fg >> 16) & 255, (fg >> 8) & 255, fg & 255))
                        lfg = fg
                    if bg != lbg:
                        app('\x1b[48;2;%d;%d;%dm' % ((bg >> 16) & 255, (bg >> 8) & 255, bg & 255))
                        lbg = bg
                    app(ch)
        sys.stdout.write(''.join(out))
        sys.stdout.flush()


# ---------------------------------------------------------------- ввод
VK = {
    'w': 0x57, 'a': 0x41, 's': 0x53, 'd': 0x44, 'q': 0x51, 'e': 0x45,
    'r': 0x52, 'm': 0x4D, 'f': 0x46, 'p': 0x50, 'y': 0x59, 'n': 0x4E,
    'left': 0x25, 'up': 0x26, 'right': 0x27, 'down': 0x28,
    'space': 0x20, 'shift': 0x10, 'ctrl': 0x11, 'esc': 0x1B, 'tab': 0x09,
    'enter': 0x0D,
    '1': 0x31, '2': 0x32, '3': 0x33, '4': 0x34, '5': 0x35, '6': 0x36,
    '7': 0x37, 'x': 0x58, 'z': 0x5A, 'g': 0x47,
    'comma': 0xBC, 'period': 0xBE,          # шаг вбок, как в оригинале
    'pgup': 0x21, 'pgdn': 0x22, 'home': 0x24, 'k': 0x4B,
    'mouse1': 0x01, 'mouse2': 0x02,
}


class Mouse:
    """Относительное движение мыши: курсор возвращается в центр окна консоли."""

    def __init__(self):
        import ctypes
        self.ct = ctypes
        self.u32 = ctypes.windll.user32
        self.k32 = ctypes.windll.kernel32
        self.enabled = False
        self.cx = self.cy = 0

    class _POINT(object):
        pass

    def _center(self):
        import ctypes

        class RECT(ctypes.Structure):
            _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long),
                        ('right', ctypes.c_long), ('bottom', ctypes.c_long)]

        hwnd = self.k32.GetConsoleWindow()
        if not hwnd:
            return None
        r = RECT()
        if not self.u32.GetWindowRect(hwnd, ctypes.byref(r)):
            return None
        if self.u32.GetForegroundWindow() != hwnd:
            return None
        return ((r.left + r.right) // 2, (r.top + r.bottom) // 2)

    def set(self, on):
        self.enabled = bool(on)
        self.u32.ShowCursor(not self.enabled)
        c = self._center()
        if c and self.enabled:
            self.u32.SetCursorPos(c[0], c[1])

    def poll(self):
        """-> (dx, dy) в пикселях экрана."""
        if not self.enabled:
            return 0, 0
        import ctypes

        class POINT(ctypes.Structure):
            _fields_ = [('x', ctypes.c_long), ('y', ctypes.c_long)]

        c = self._center()
        if c is None:
            return 0, 0
        p = POINT()
        if not self.u32.GetCursorPos(ctypes.byref(p)):
            return 0, 0
        dx = p.x - c[0]
        dy = p.y - c[1]
        if dx or dy:
            self.u32.SetCursorPos(c[0], c[1])
        return dx, dy


class WinInput:
    """Реальное состояние клавиш через GetAsyncKeyState - без задержки автоповтора."""

    def __init__(self):
        import ctypes
        self._gaks = ctypes.windll.user32.GetAsyncKeyState
        self._prev = set()
        self._now = set()

    def poll(self):
        import msvcrt
        while msvcrt.kbhit():          # гасим эхо в консоли
            msvcrt.getwch()
        self._prev = self._now
        now = set()
        gaks = self._gaks
        for name, vk in VK.items():
            if gaks(vk) & 0x8000:
                now.add(name)
        self._now = now

    def down(self, k):
        return k in self._now

    def hit(self, k):
        return k in self._now and k not in self._prev

    def restore(self):
        pass


class PosixInput:
    """Запасной вариант: чтение stdin с удержанием клавиши 0.22 с."""

    SEQ = {'\x1b[A': 'up', '\x1b[B': 'down', '\x1b[C': 'right', '\x1b[D': 'left'}

    def __init__(self):
        import termios
        import tty
        self._termios = termios
        self.fd = sys.stdin.fileno()
        self.old = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)
        self.times = {}
        self._prev = set()
        self._now = set()
        self._buf = ''

    def poll(self):
        import select
        while select.select([sys.stdin], [], [], 0)[0]:
            self._buf += sys.stdin.read(1)
        while self._buf:
            k = None
            if self._buf[0] == '\x1b' and len(self._buf) >= 3 and self._buf[:3] in self.SEQ:
                k = self.SEQ[self._buf[:3]]
                self._buf = self._buf[3:]
            else:
                ch = self._buf[0]
                self._buf = self._buf[1:]
                if ch == '\x1b':
                    k = 'esc'
                elif ch == ' ':
                    k = 'space'
                elif ch in ('\r', '\n'):
                    k = 'enter'
                elif ch == '\t':
                    k = 'tab'
                elif ch == ',':
                    k = 'comma'
                elif ch == '.':
                    k = 'period'
                elif ch.lower() in VK:
                    k = ch.lower()
            if k:
                self.times[k] = time.time()
        t = time.time()
        self._prev = self._now
        self._now = {k for k, v in self.times.items() if t - v < 0.22}

    def down(self, k):
        return k in self._now

    def hit(self, k):
        return k in self._now and k not in self._prev

    def restore(self):
        self._termios.tcsetattr(self.fd, self._termios.TCSADRAIN, self.old)


class NullInput:
    def poll(self):
        pass

    def down(self, k):
        return False

    def hit(self, k):
        return False

    def restore(self):
        pass


def make_input(headless=False):
    if headless:
        return NullInput()
    if IS_WIN:
        return WinInput()
    try:
        return PosixInput()
    except Exception:
        return NullInput()
