# Box *full* of Life

<p align="center">
<img src="https://github.com/ah01/box-of-life/raw/master/doc/box.gif">
</p>

Modification of [Ikea FREKVENS](https://www.ikea.com/cz/en/p/frekvens-led-multi-use-lighting-black-30420354/)
with an **ESP32** that plays [Conway's **Game of Life**](https://en.wikipedia.org/wiki/Conway%27s_Game_of_Life),
a handful of other animations, and anything you upload to it as pixel art.

Everything is controlled from a small web page that the box itself serves — no app, no cloud, no
external dependencies.

## Features

- **Animations**: Game of Life, rain, bouncing ball, starfield, plasma, expanding rings,
  scrolling text and an NTP clock.
  - Game of Life restarts itself when the field becomes stable or turns into a period 2
    [oscillator](https://conwaylife.com/wiki/Oscillator).
- **Web UI** on port 80: switch animations, set brightness and speed, change the scrolling text,
  live preview of what is currently on the panel.
- **Upload images and GIFs**: drop a PNG/JPG/WebP/GIF onto the page, tune it, and it plays on the
  panel. Animated GIFs keep their per frame timing.
- **Buttons** keep working like before:
  - Red button — *short press* cycle brightness, *long press* on/off
  - Yellow button — *short press* next animation, *long press* restart the current one
- Settings and uploaded animations survive a reboot.

### How image conversion works

The panel is 16×16 and **one bit per pixel** — a pixel is either on or off, and brightness is global
for the whole panel. All the decoding, scaling and dithering therefore happens **in your browser**:
the page decodes the GIF (including transparency, partial frames and interlacing), scales each frame
to 16×16, converts it to 1 bit, and uploads only the finished 32 bytes per frame. The ESP32 never has
to deal with image formats, which keeps both the RAM use and the firmware small.

You can pick the dithering (Floyd-Steinberg, Atkinson, Bayer 4×4 or a hard threshold), threshold,
contrast, brightness, scaling mode, rotation and mirroring, and watch the result animate live before
you save it.

## Firmware

Written in [MicroPython](https://micropython.org/download/ESP32_GENERIC/), **1.20 or newer**
(`framebuf.ellipse()` and `network.hostname()` are used).

```bash
cd src
# copy everything (.) into the remote (:)
mpremote cp -r . :
# run main.py to see stdout
mpremote run main.py
```

Layout of `src`:

| File | Purpose |
|------|---------|
| `config.py` | pin assignment and limits — **start here** |
| `display.py` | SPI driver for the panel, `Screen` (a `framebuf.FrameBuffer`) |
| `game.py` | one generation of Conway's Game of Life |
| `animations.py` | all animations plus the player for uploaded ones |
| `player.py` | current mode, brightness, speed, persistence |
| `server.py` | async HTTP server and JSON API |
| `wifi.py` | station mode with access point fallback |
| `storage.py` | uploaded animations on the flash file system |
| `button.py` | debounced short/long press handling |
| `www/index.html` | the whole web UI (no external resources) |

### First start

1. On first boot there are no WiFi credentials, so the box opens its own access point
   **`Box-of-Life`** (password `boxoflife`).
2. Connect to it and open <http://192.168.4.1/>.
3. Under *System → WLAN einrichten* enter your network. The box reboots and joins it.
4. After that it is reachable at its IP, and usually also at <http://boxoflife.local/>.

If the configured network is unavailable it falls back to the access point again, so you can never
lock yourself out.

> ⚠ The web interface has **no authentication**. It is meant for a trusted home network — do not
> forward the port to the internet.

## Ikea FREKVENS HW Modification

Disassemble the box, remove the original MCU board and connect the ESP32. Steps:

1. Disassembly — there are tutorials already, e.g.
   [here](https://spritesmods.com/?art=frekvens&page=2) or
   [here](https://github.com/frumperino/FrekvensPanel/blob/master/frekvens-hacking.pdf)
2. Remove the original MCU (green) PCB and solder a connector in its place (or wire it up directly
   according to the table below).

### Connection

Pin numbers are for a classic ESP32 DevKit (WROOM-32); change them in `config.py` for other boards.

| Board     | Pin/Wire   | ESP32 GPIO | Note                  |
|-----------|------------|------------|-----------------------|
| LED PCB   | 1 (Vcc)    | 5V / VIN   | see power note below  |
| LED PCB   | 2          | GPIO 22    | En (brightness PWM)   |
| LED PCB   | 3          | GPIO 23    | Data (SPI MOSI)       |
| LED PCB   | 4          | GPIO 18    | Clk (SPI SCK)         |
| LED PCB   | 5          | GPIO 21    | Latch                 |
| LED PCB   | 6 (Gnd)    | GND        |                       |
| Buttons   | Red wire   | GND        |                       |
| Buttons   | Black wire | GPIO 32    | Yellow button         |
| Buttons   | White wire | GPIO 33    | Red button            |

GPIO 19 is claimed by the SPI peripheral as MISO and stays unconnected.

**Power:** the FREKVENS supply delivers roughly 4 V. The Pico could take that on `VSYS`, but a
typical ESP32 board has an AMS1117 regulator that needs ~5 V to produce a stable 3.3 V. Either power
the ESP32 from USB / a separate 5 V supply (sharing GND with the panel), or feed a regulated 3.3 V
straight to the `3V3` pin. Do not feed 4 V into `3V3`.

The panel is happy with the 3.3 V logic levels of the ESP32, same as with the Pico.

## API

The web page is just a client for this — handy for scripting.

| Method | Path | Body / query |
|--------|------|--------------|
| `GET`  | `/api/state` | full state: settings, built-ins, uploads |
| `POST` | `/api/state` | partial JSON, e.g. `{"mode":"plasma","brightness":80}` |
| `GET`  | `/api/frame` | the 32 bytes currently on the panel |
| `GET`  | `/api/anim?name=x` | raw animation file |
| `POST` | `/api/upload?name=x&play=1` | animation file as `application/octet-stream` |
| `POST` | `/api/delete` | `{"name": "x"}` |
| `POST` | `/api/wifi` | `{"ssid": "...", "password": "..."}`, reboots |
| `POST` | `/api/reboot` | |

Modes are the built-in ids (`life`, `rain`, `bounce`, `stars`, `plasma`, `rings`, `text`, `clock`)
or `file:<name>` for an upload.

```bash
curl -X POST -H 'Content-Type: application/json' \
     -d '{"mode":"clock","brightness":40}' http://boxoflife.local/api/state
```

### Animation file format

Little endian, `/anim/<name>.anm`:

```
offset  size  content
0       4     magic "FRK1"
4       1     version (1)
5       1     flags (reserved)
6       2     frame count
8       2     default frame delay in ms
10      2     reserved
12      ...   frames: 2 bytes delay in ms + 32 bytes pixel data
```

The 32 pixel bytes use the panel's own layout (`framebuf.MONO_VLSB`): byte `(y // 8) * 16 + x`,
bit `y % 8`.

## Ideas for improvements

- Add predefined startup patterns (e.g. glider)
- Playlists that cycle through several animations
- A pixel editor in the web UI
- Gzip `www/index.html` (the server already serves `index.html.gz` if it exists)
