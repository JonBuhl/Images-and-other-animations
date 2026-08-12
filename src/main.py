import gc

import asyncio

import config
import display
import server
import storage
import wifi
from player import Player


async def network_task(player):
    """Bring up WiFi and the web server without blocking the animation."""
    try:
        player.net = await wifi.start()
        await server.start(player)
    except Exception as e:
        print("network setup failed:", e)


async def gc_task():
    while True:
        gc.collect()
        gc.threshold(gc.mem_free() // 4 + gc.mem_alloc())
        await asyncio.sleep(10)


def setup_buttons(player):
    from machine import Pin
    from button import create_btn_task

    mode_btn = Pin(config.PIN_BTN_MODE, Pin.IN, Pin.PULL_UP)
    pwr_btn = Pin(config.PIN_BTN_PWR, Pin.IN, Pin.PULL_UP)
    # yellow: short = next animation, long = restart current one
    asyncio.create_task(create_btn_task(mode_btn, player.next_mode, player.restart))
    # red: short = cycle brightness, long = on/off
    asyncio.create_task(create_btn_task(pwr_btn, player.cycle_brightness, player.toggle_power))


async def main():
    storage.ensure_dir()

    player = Player(display.Screen())
    player.load_settings()

    if config.BUTTONS_ENABLED:
        setup_buttons(player)

    asyncio.create_task(gc_task())
    asyncio.create_task(player.settings_saver())
    asyncio.create_task(network_task(player))

    await player.run()


print("Start main")
try:
    asyncio.run(main())
finally:
    display.blank()
    asyncio.new_event_loop()
