"""WiFi bring-up: join the configured network, fall back to an access point."""

import json
import network

import asyncio

import config

status = {"mode": "none", "ssid": None, "ip": "0.0.0.0", "ntp": False}


def load_credentials():
    try:
        with open(config.WIFI_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_credentials(ssid, password):
    with open(config.WIFI_FILE, "w") as f:
        json.dump({"ssid": ssid, "password": password}, f)


def _set_hostname(sta):
    try:
        network.hostname(config.HOSTNAME)
        return
    except Exception:
        pass
    try:  # older firmware
        sta.config(dhcp_hostname=config.HOSTNAME)
    except Exception:
        pass


async def _sync_time():
    import ntptime
    try:
        ntptime.timeout = 3
    except Exception:
        pass
    for _ in range(3):
        try:
            ntptime.settime()
            status["ntp"] = True
            return
        except Exception:
            await asyncio.sleep(2)
    print("NTP sync failed")


async def _connect_station(cred):
    ssid = cred.get("ssid")
    if not ssid:
        return False
    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    _set_hostname(sta)
    print("connecting to", ssid)
    sta.connect(ssid, cred.get("password", ""))
    for _ in range(config.WIFI_TIMEOUT * 2):
        if sta.isconnected():
            break
        await asyncio.sleep_ms(500)
    if not sta.isconnected():
        print("connection failed")
        sta.active(False)
        return False
    status["mode"] = "sta"
    status["ssid"] = ssid
    status["ip"] = sta.ifconfig()[0]
    print("connected:", status["ip"])
    return True


def _start_ap():
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    try:
        ap.config(essid=config.AP_SSID, password=config.AP_PASSWORD,
                  authmode=network.AUTH_WPA_WPA2_PSK)
    except Exception:
        ap.config(essid=config.AP_SSID, password=config.AP_PASSWORD)
    status["mode"] = "ap"
    status["ssid"] = config.AP_SSID
    status["ip"] = ap.ifconfig()[0]
    print("access point up:", config.AP_SSID, status["ip"])


async def start():
    if await _connect_station(load_credentials()):
        await _sync_time()
    else:
        _start_ap()
    return status
