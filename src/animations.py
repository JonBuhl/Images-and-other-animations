"""The animations the box can play.

Every animation is a class with an async `run()` that loops forever and calls
`screen.show()` whenever it has drawn a new frame. Pacing goes through
`self.wait()` so the global speed setting applies everywhere. The player
cancels the task when the mode changes, so `run()` never has to return.
"""

import math
import random
import time

import asyncio

import display
import storage
from game import next_gen


class Animation:
    name = "base"
    label = "Base"
    delay = 50  # ms between frames at speed 1.0

    def __init__(self, player):
        self.player = player
        self.screen = player.screen

    async def wait(self, ms=None):
        await self.player.sleep(self.delay if ms is None else ms)

    async def run(self):
        raise NotImplementedError


# --- Game of Life ------------------------------------------------------------

class LifeAnimation(Animation):
    name = "life"
    label = "Game of Life"
    delay = 50

    def __init__(self, player):
        super().__init__(player)
        self.buffers = [self.screen, display.Screen(), display.Screen()]

    async def restart(self):
        buffers = self.buffers
        await self.wait(self.delay * 2)
        buffers[0].clear()
        buffers[0].show()
        await self.wait(self.delay * 2)
        # Fill random and calculate the first generation without showing it:
        # the step between a random field and its first generation is a big
        # visual jump, so we start with the second one.
        buffers[2].fill_random()
        await next_gen(buffers[2], buffers[0])
        buffers[0].show()

    async def run(self):
        buffers = self.buffers
        bi = 0   # current buffer index
        osc = 0  # oscillation counter, we let it oscillate a while and restart
        await self.restart()
        while True:
            ni = (bi + 1) % 3
            await next_gen(buffers[bi], buffers[ni])
            buffers[ni].show()

            # detect stable fields and period 2 oscillators
            if buffers[bi] == buffers[ni]:
                await self.restart()
                ni = 0
            elif buffers[0] == buffers[2]:
                osc += 1
                if osc >= 3:
                    await self.restart()
                    ni = 0
                    osc = 0

            bi = ni
            await self.wait()


# --- Rain --------------------------------------------------------------------

class RainAnimation(Animation):
    name = "rain"
    label = "Regen"
    delay = 70

    async def run(self):
        s = self.screen
        # every drop is [x, head y, length, ticks per step, tick counter]
        drops = [[random.getrandbits(4), random.randrange(-16, 0),
                  random.randrange(2, 6), random.randrange(1, 3), 0]
                 for _ in range(11)]
        while True:
            s.clear()
            for d in drops:
                d[4] += 1
                if d[4] >= d[3]:
                    d[4] = 0
                    d[1] += 1
                if d[1] - d[2] > 16:
                    d[0] = random.getrandbits(4)
                    d[1] = random.randrange(-6, 0)
                    d[2] = random.randrange(2, 6)
                    d[3] = random.randrange(1, 3)
                for k in range(d[2]):
                    y = d[1] - k
                    if 0 <= y < 16:
                        s.pixel(d[0], y, 1)
            s.show()
            await self.wait()


# --- Bouncing ball -----------------------------------------------------------

class BounceAnimation(Animation):
    name = "bounce"
    label = "Ball"
    delay = 60

    async def run(self):
        s = self.screen
        x, y = 7.0, 7.0
        dx, dy = 0.9, 0.62
        while True:
            x += dx
            y += dy
            if x <= 1 or x >= 13:
                dx = -dx
                x = max(1, min(13, x))
            if y <= 1 or y >= 13:
                dy = -dy
                y = max(1, min(13, y))
            s.clear()
            s.rect(0, 0, 16, 16, 1)
            s.ellipse(int(x) + 1, int(y) + 1, 1, 1, 1, True)
            s.show()
            await self.wait()


# --- Starfield ---------------------------------------------------------------

class StarsAnimation(Animation):
    name = "stars"
    label = "Sternenflug"
    delay = 60

    def _new_star(self):
        return [random.randrange(-64, 64), random.randrange(-64, 64),
                random.randrange(16, 64)]

    async def run(self):
        s = self.screen
        stars = [self._new_star() for _ in range(26)]
        while True:
            s.clear()
            for st in stars:
                st[2] -= 3
                if st[2] < 4:
                    st[0], st[1], st[2] = self._new_star()
                    st[2] = 63
                x = 8 + (st[0] * 8) // st[2]
                y = 8 + (st[1] * 8) // st[2]
                if 0 <= x < 16 and 0 <= y < 16:
                    s.pixel(x, y, 1)
                    if st[2] < 16:  # near stars get a little bigger
                        if x + 1 < 16:
                            s.pixel(x + 1, y, 1)
                        if y + 1 < 16:
                            s.pixel(x, y + 1, 1)
                else:
                    st[0], st[1], st[2] = self._new_star()
                    st[2] = 63
            s.show()
            await self.wait()


# --- Plasma ------------------------------------------------------------------

# 64 step sine, scaled to 0..15, and a 4x4 ordered dither matrix
_SIN = bytes(int(8 + 7.5 * math.sin(i * math.pi / 32)) for i in range(64))
_BAYER = (0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5)


class PlasmaAnimation(Animation):
    name = "plasma"
    label = "Plasma"
    delay = 60

    async def run(self):
        s = self.screen
        t = 0
        while True:
            for y in range(16):
                for x in range(16):
                    v = (_SIN[(x * 3 + t) & 63]
                         + _SIN[(y * 4 - t) & 63]
                         + _SIN[((x + y) * 2 + (t >> 1)) & 63])
                    # ordered dither: 0..45 value against a 4x4 threshold grid
                    s.pixel(x, y, 1 if v > 14 + _BAYER[(y & 3) * 4 + (x & 3)] else 0)
                await asyncio.sleep(0)
            s.show()
            t += 1
            await self.wait()


# --- Expanding rings ---------------------------------------------------------

class RingsAnimation(Animation):
    name = "rings"
    label = "Ringe"
    delay = 70

    async def run(self):
        s = self.screen
        rings = []  # [cx, cy, radius]
        cooldown = 0
        while True:
            s.clear()
            cooldown -= 1
            if cooldown <= 0:
                rings.append([random.randrange(3, 13), random.randrange(3, 13), 0])
                cooldown = random.randrange(3, 7)
            for r in rings:
                r[2] += 1
                s.ellipse(r[0], r[1], r[2], r[2], 1)
            rings = [r for r in rings if r[2] < 22]
            s.show()
            await self.wait()


# --- Scrolling text ----------------------------------------------------------

class TextAnimation(Animation):
    name = "text"
    label = "Lauftext"
    delay = 90

    async def run(self):
        s = self.screen
        while True:
            text = self.player.text or "BOX OF LIFE"
            width = len(text) * 8
            x = 16
            while x > -width:
                # re-read the text only between runs so it does not tear
                s.clear()
                s.text(text, x, 4, 1)
                s.show()
                x -= 1
                await self.wait()
                if self.player.text != text:
                    break
            await self.wait(self.delay * 4)


# --- Clock -------------------------------------------------------------------

_WD_T = (0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4)


def _weekday(y, m, d):
    """Day of week (0 = Sunday .. 6 = Saturday) — Sakamoto's algorithm."""
    if m < 3:
        y -= 1
    return (y + y // 4 - y // 100 + y // 400 + _WD_T[m - 1] + d) % 7


def _is_dst(tm):
    """European summer time (CEST): from the last Sunday of March 01:00 UTC
    until the last Sunday of October 01:00 UTC."""
    year, month, day, hour = tm[0], tm[1], tm[2], tm[3]
    last_mar = 31 - _weekday(year, 3, 31)
    last_oct = 31 - _weekday(year, 10, 31)
    if month < 3 or month > 10:
        return False
    if 3 < month < 10:
        return True
    if month == 3:
        if day > last_mar:
            return True
        return day == last_mar and hour >= 1
    # October
    if day < last_oct:
        return True
    return day == last_oct and hour < 1


class ClockAnimation(Animation):
    name = "clock"
    label = "Uhr"
    delay = 500

    async def run(self):
        s = self.screen
        while True:
            t = time.time()
            offset = int(self.player.tz * 3600)
            if _is_dst(time.localtime(t)):
                offset += 3600
            now = time.localtime(t + offset)
            s.clear()
            if self.player.net.get("ntp"):
                s.text("{:02d}".format(now[3]), 0, 0, 1)
                s.text("{:02d}".format(now[4]), 0, 8, 1)
                # blinking separator in the free pixel column between the digits
                if now[5] & 1:
                    s.pixel(15, 7, 1)
                    s.pixel(15, 8, 1)
            else:
                s.text("--", 0, 0, 1)
                s.text("--", 0, 8, 1)
            s.show()
            await self.wait()


# --- Uploaded animations -----------------------------------------------------

class FileAnimation(Animation):
    name = "file"
    label = "Upload"
    delay = 100

    def __init__(self, player, fname):
        super().__init__(player)
        self.fname = fname

    async def run(self):
        path = storage.path_for(self.fname)
        count = storage.validate(path)
        if count < 0:
            raise OSError("broken animation: " + self.fname)

        record = bytearray(storage.FRAME_SIZE)
        pixels = memoryview(record)[2:]
        f = open(path, "rb")
        try:
            while True:
                f.seek(storage.HEADER_SIZE)
                for _ in range(count):
                    if f.readinto(record) != storage.FRAME_SIZE:
                        break
                    self.screen.load(pixels)
                    self.screen.show()
                    delay = record[0] | (record[1] << 8)
                    await self.wait(delay if delay else self.delay)
                if count == 1:
                    # a single still image, no need to spin through the file
                    await self.wait(1000)
        finally:
            f.close()


# --- Registry ----------------------------------------------------------------

BUILTINS = (
    LifeAnimation,
    RainAnimation,
    BounceAnimation,
    StarsAnimation,
    PlasmaAnimation,
    RingsAnimation,
    TextAnimation,
    ClockAnimation,
)

_BY_NAME = {cls.name: cls for cls in BUILTINS}


def builtin_list():
    return [{"id": cls.name, "label": cls.label} for cls in BUILTINS]


def create(player, mode):
    """Build an animation instance from a mode string.

    Built-ins are addressed by their name, uploaded animations as
    `file:<name>`.
    """
    if mode.startswith("file:"):
        return FileAnimation(player, mode[5:])
    cls = _BY_NAME.get(mode)
    if cls is None:
        return None
    return cls(player)


def is_valid(mode):
    if mode.startswith("file:"):
        return storage.exists(mode[5:])
    return mode in _BY_NAME
