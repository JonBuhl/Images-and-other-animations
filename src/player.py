"""Owns the panel state: which animation runs, how bright, how fast."""

import json

import asyncio

import animations
import config
import display
import storage

DEFAULTS = {
    "mode": "life",
    "brightness": 60,
    "speed": 1.0,
    "text": "BOX OF LIFE",
    "tz": 1.0,
    "on": True,
    "rotate": config.DISPLAY_ROTATE,
    "mirror": config.DISPLAY_MIRROR,
}

BRIGHTNESS_STEPS = (100, 60, 30, 10)


class Player:

    def __init__(self, screen):
        self.screen = screen
        self.mode = DEFAULTS["mode"]
        self.brightness = DEFAULTS["brightness"]
        self.speed = DEFAULTS["speed"]
        self.text = DEFAULTS["text"]
        self.tz = DEFAULTS["tz"]
        self.on = DEFAULTS["on"]
        self.rotate = DEFAULTS["rotate"]
        self.mirror = DEFAULTS["mirror"]
        display.set_orientation(self.rotate, self.mirror)
        self.net = {"mode": "none", "ssid": None, "ip": "0.0.0.0", "ntp": False}
        self._change = asyncio.Event()
        self._dirty = False

    # --- pacing --------------------------------------------------------------

    async def sleep(self, ms):
        """Sleep `ms` milliseconds, scaled by the global speed factor."""
        ms = int(ms / self.speed)
        await asyncio.sleep_ms(ms if ms > 0 else 1)

    # --- state ---------------------------------------------------------------

    def state(self):
        return {
            "on": self.on,
            "mode": self.mode,
            "brightness": self.brightness,
            "speed": self.speed,
            "text": self.text,
            "tz": self.tz,
            "rotate": self.rotate,
            "mirror": self.mirror,
            "net": self.net,
            "builtins": animations.builtin_list(),
            "animations": storage.list_animations(),
            "free": storage.free_space(),
            "max_frames": config.MAX_FRAMES,
        }

    def apply(self, data):
        """Apply a partial state update coming from the web UI."""
        restart = False

        if "on" in data:
            on = bool(data["on"])
            if on != self.on:
                self.on = on
                restart = True

        if "brightness" in data:
            self.brightness = max(0, min(100, int(data["brightness"])))
            if self.on:
                display.set_brightness(self.brightness)

        if "speed" in data:
            self.speed = max(0.1, min(8.0, float(data["speed"])))

        if "text" in data:
            self.text = str(data["text"])[:64]

        if "tz" in data:
            self.tz = max(-12.0, min(14.0, float(data["tz"])))

        if "rotate" in data:
            r = int(data["rotate"])
            if r not in (0, 90, 180, 270):
                raise ValueError("rotate must be 0, 90, 180 or 270")
            self.rotate = r

        if "mirror" in data:
            self.mirror = bool(data["mirror"])

        if "rotate" in data or "mirror" in data:
            display.set_orientation(self.rotate, self.mirror)

        if "mode" in data:
            mode = str(data["mode"])
            if animations.is_valid(mode):
                if mode != self.mode:
                    self.mode = mode
                    restart = True
                elif not self.on:
                    self.on = True
                    restart = True
            else:
                raise ValueError("unknown mode: " + mode)

        self._dirty = True
        if restart:
            self._change.set()
        return restart

    def mode_list(self):
        modes = [cls.name for cls in animations.BUILTINS]
        modes += ["file:" + a["name"] for a in storage.list_animations()]
        return modes

    # --- button handlers -----------------------------------------------------

    def next_mode(self):
        modes = self.mode_list()
        try:
            i = modes.index(self.mode)
        except ValueError:
            i = -1
        self.mode = modes[(i + 1) % len(modes)]
        self.on = True
        self._dirty = True
        self._change.set()

    def restart(self):
        self._change.set()

    def cycle_brightness(self):
        if not self.on:
            self.on = True
            self._change.set()
            return
        steps = BRIGHTNESS_STEPS
        # pick the next step below the current brightness, wrapping around
        nxt = steps[0]
        for s in steps:
            if s < self.brightness:
                nxt = s
                break
        self.brightness = nxt
        display.set_brightness(nxt)
        self._dirty = True

    def toggle_power(self):
        self.on = not self.on
        self._dirty = True
        self._change.set()

    # --- persistence ---------------------------------------------------------

    def load_settings(self):
        try:
            with open(config.SETTINGS_FILE) as f:
                data = json.load(f)
        except Exception:
            return
        for key in DEFAULTS:
            if key in data:
                try:
                    setattr(self, key, type(DEFAULTS[key])(data[key]))
                except Exception:
                    pass
        if not animations.is_valid(self.mode):
            self.mode = DEFAULTS["mode"]
        if self.rotate not in (0, 90, 180, 270):
            self.rotate = DEFAULTS["rotate"]
        display.set_orientation(self.rotate, self.mirror)

    def save_settings(self):
        data = {key: getattr(self, key) for key in DEFAULTS}
        try:
            with open(config.SETTINGS_FILE, "w") as f:
                json.dump(data, f)
        except OSError as e:
            print("could not save settings:", e)

    async def settings_saver(self):
        """Write settings to flash at most every few seconds."""
        while True:
            await asyncio.sleep(5)
            if self._dirty:
                self._dirty = False
                self.save_settings()

    # --- main loop -----------------------------------------------------------

    async def _run_animation(self, anim):
        try:
            await anim.run()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print("animation '{}' failed: {}".format(self.mode, e))
            # do not leave the box dark on a broken animation
            self.mode = DEFAULTS["mode"]
            self._change.set()

    async def run(self):
        while True:
            self._change.clear()
            task = None

            if self.on:
                anim = animations.create(self, self.mode)
                if anim is None:
                    self.mode = DEFAULTS["mode"]
                    anim = animations.create(self, self.mode)
                display.set_brightness(self.brightness)
                print("play:", self.mode)
                task = asyncio.create_task(self._run_animation(anim))
            else:
                print("power off")
                display.set_brightness(0)
                self.screen.clear()
                display.blank()

            await self._change.wait()

            if task is not None:
                task.cancel()
                await asyncio.sleep_ms(0)
