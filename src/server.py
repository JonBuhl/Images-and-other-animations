"""A small async HTTP server for controlling the box.

Endpoints:

    GET  /                 web UI
    GET  /api/state        full state (settings, built-ins, uploads)
    POST /api/state        partial state update, JSON body
    POST /api/message      show a scrolling custom message, {"message": "..."}
    POST /api/rotate       set clockwise rotation, {"rotate": 90}
    POST /api/mirror       set horizontal mirror, {"mirror": true}
    GET  /api/frame        the 32 raw bytes currently on the panel
    GET  /api/anim?name=   raw animation file (used for the browser preview)
    POST /api/upload?name= upload an animation (binary, see storage.py)
    POST /api/delete       {"name": ...}
    POST /api/wifi         {"ssid": ..., "password": ...}, reboots
    POST /api/reboot

There is no authentication: this is meant for a trusted home network.
"""

import json
import os

import asyncio

import config
import storage

WWW_DIR = "/www"

_CONTENT_TYPES = {
    "html": "text/html; charset=utf-8",
    "js": "application/javascript",
    "css": "text/css",
    "ico": "image/x-icon",
    "png": "image/png",
    "svg": "image/svg+xml",
}

_player = None


# --- helpers -----------------------------------------------------------------

def _unquote(s):
    if "%" not in s and "+" not in s:
        return s
    s = s.replace("+", " ")
    parts = s.split("%")
    out = parts[0]
    for p in parts[1:]:
        try:
            out += chr(int(p[:2], 16)) + p[2:]
        except ValueError:
            out += "%" + p
    return out


def _split_query(target):
    if "?" in target:
        path, qs = target.split("?", 1)
    else:
        path, qs = target, ""
    query = {}
    for part in qs.split("&"):
        if not part:
            continue
        if "=" in part:
            k, v = part.split("=", 1)
        else:
            k, v = part, ""
        query[_unquote(k)] = _unquote(v)
    return path, query


async def _respond(writer, status, ctype, body=b"", extra=""):
    if isinstance(body, str):
        body = body.encode()
    head = ("HTTP/1.1 {}\r\n"
            "Content-Type: {}\r\n"
            "Content-Length: {}\r\n"
            "Cache-Control: no-store\r\n"
            "Connection: close\r\n"
            "{}\r\n").format(status, ctype, len(body), extra)
    writer.write(head.encode())
    if body:
        writer.write(body)
    await writer.drain()


async def _json_response(writer, obj, status="200 OK"):
    await _respond(writer, status, "application/json", json.dumps(obj))


async def _error(writer, status, message):
    await _json_response(writer, {"error": message}, status)


async def _send_file(writer, path, ctype):
    encoding = ""
    try:
        os.stat(path + ".gz")
        path += ".gz"
        encoding = "Content-Encoding: gzip\r\n"
    except OSError:
        pass
    try:
        size = os.stat(path)[6]
    except OSError:
        await _error(writer, "404 Not Found", "not found")
        return
    head = ("HTTP/1.1 200 OK\r\n"
            "Content-Type: {}\r\n"
            "Content-Length: {}\r\n"
            "{}"
            "Cache-Control: no-cache\r\n"
            "Connection: close\r\n\r\n").format(ctype, size, encoding)
    writer.write(head.encode())
    await writer.drain()
    buf = bytearray(512)
    with open(path, "rb") as f:
        while True:
            n = f.readinto(buf)
            if not n:
                break
            writer.write(buf[:n])
            await writer.drain()


async def _discard(reader, n):
    while n > 0:
        chunk = await reader.read(min(512, n))
        if not chunk:
            return
        n -= len(chunk)


async def _read_body(reader, headers, limit):
    """Read the request body, or None if it is missing or too large."""
    try:
        n = int(headers.get("content-length", "0"))
    except ValueError:
        return None
    if n <= 0:
        return None
    if n > limit:
        await _discard(reader, n)
        return None
    return await reader.readexactly(n)


async def _read_json(reader, writer, headers):
    body = await _read_body(reader, headers, config.MAX_JSON)
    if body is None:
        await _error(writer, "400 Bad Request", "missing or oversized body")
        return None
    try:
        return json.loads(body)
    except Exception:
        await _error(writer, "400 Bad Request", "invalid JSON")
        return None


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


async def _reboot_soon():
    import machine
    await asyncio.sleep(1)
    machine.reset()


# --- routes ------------------------------------------------------------------

async def _handle_upload(reader, writer, query, headers):
    name = storage.sanitize(query.get("name", ""))
    try:
        length = int(headers.get("content-length", "0"))
    except ValueError:
        length = 0

    if name is None or length <= 0 or length > config.MAX_UPLOAD:
        await _discard(reader, length)
        await _error(writer, "400 Bad Request", "invalid name or size")
        return

    storage.ensure_dir()
    tmp = storage.ANIM_DIR + "/.upload"
    remaining = length
    try:
        with open(tmp, "wb") as f:
            while remaining > 0:
                chunk = await reader.read(min(512, remaining))
                if not chunk:
                    break
                f.write(chunk)
                remaining -= len(chunk)
    except OSError as e:
        _remove(tmp)
        await _error(writer, "507 Insufficient Storage", "write failed: {}".format(e))
        return

    if remaining > 0:
        _remove(tmp)
        await _error(writer, "400 Bad Request", "incomplete upload")
        return

    count = storage.validate(tmp)
    if count < 0:
        _remove(tmp)
        await _error(writer, "400 Bad Request", "not a valid animation file")
        return

    target = storage.path_for(name)
    _remove(target)
    os.rename(tmp, target)

    if query.get("play") == "1":
        _player.apply({"mode": "file:" + name, "on": True})

    await _json_response(writer, {"ok": True, "name": name, "frames": count})


async def _route(reader, writer):
    line = await reader.readline()
    if not line:
        return
    try:
        method, target, _ = line.decode().split(" ", 2)
    except ValueError:
        await _error(writer, "400 Bad Request", "malformed request")
        return

    headers = {}
    while True:
        h = await reader.readline()
        if not h or h == b"\r\n":
            break
        try:
            k, v = h.decode().split(":", 1)
            headers[k.strip().lower()] = v.strip()
        except ValueError:
            pass

    path, query = _split_query(target)

    # --- static ---
    if method == "GET" and path in ("/", "/index.html"):
        await _send_file(writer, WWW_DIR + "/index.html", _CONTENT_TYPES["html"])
        return

    # --- state ---
    if path == "/api/state":
        if method == "GET":
            await _json_response(writer, _player.state())
            return
        if method == "POST":
            data = await _read_json(reader, writer, headers)
            if data is None:
                return
            try:
                _player.apply(data)
            except (ValueError, TypeError) as e:
                await _error(writer, "400 Bad Request", str(e))
                return
            await _json_response(writer, _player.state())
            return

    # --- custom message ---
    if method == "POST" and path == "/api/message":
        data = await _read_json(reader, writer, headers)
        if data is None:
            return
        msg = str(data.get("message", "")).strip()
        if not msg:
            await _error(writer, "400 Bad Request", "missing message")
            return
        _player.apply({"text": msg[:64], "mode": "text", "on": True})
        await _json_response(writer, _player.state())
        return

    # --- orientation ---
    if method == "POST" and path == "/api/rotate":
        data = await _read_json(reader, writer, headers)
        if data is None:
            return
        if "rotate" not in data:
            await _error(writer, "400 Bad Request", "missing rotate")
            return
        try:
            _player.apply({"rotate": data["rotate"]})
        except (ValueError, TypeError) as e:
            await _error(writer, "400 Bad Request", str(e))
            return
        await _json_response(writer, _player.state())
        return

    if method == "POST" and path == "/api/mirror":
        data = await _read_json(reader, writer, headers)
        if data is None:
            return
        if "mirror" not in data:
            await _error(writer, "400 Bad Request", "missing mirror")
            return
        _player.apply({"mirror": data["mirror"]})
        await _json_response(writer, _player.state())
        return

    # --- live view of the panel ---
    if method == "GET" and path == "/api/frame":
        await _respond(writer, "200 OK", "application/octet-stream",
                       bytes(_player.screen.buffer))
        return

    # --- animation files ---
    if method == "GET" and path == "/api/anim":
        name = storage.sanitize(query.get("name", ""))
        if name is None or not storage.exists(name):
            await _error(writer, "404 Not Found", "unknown animation")
            return
        await _send_file(writer, storage.path_for(name), "application/octet-stream")
        return

    if method == "POST" and path == "/api/upload":
        await _handle_upload(reader, writer, query, headers)
        return

    if method == "POST" and path == "/api/delete":
        data = await _read_json(reader, writer, headers)
        if data is None:
            return
        name = storage.sanitize(data.get("name", ""))
        if name is None or not storage.delete(name):
            await _error(writer, "404 Not Found", "unknown animation")
            return
        if _player.mode == "file:" + name:
            _player.apply({"mode": "life"})
        await _json_response(writer, _player.state())
        return

    # --- system ---
    if method == "POST" and path == "/api/wifi":
        data = await _read_json(reader, writer, headers)
        if data is None:
            return
        ssid = str(data.get("ssid", "")).strip()
        if not ssid:
            await _error(writer, "400 Bad Request", "missing ssid")
            return
        import wifi
        wifi.save_credentials(ssid, str(data.get("password", "")))
        _player.save_settings()
        await _json_response(writer, {"ok": True, "reboot": True})
        asyncio.create_task(_reboot_soon())
        return

    if method == "POST" and path == "/api/reboot":
        await _discard(reader, int(headers.get("content-length", "0") or 0))
        _player.save_settings()
        await _json_response(writer, {"ok": True, "reboot": True})
        asyncio.create_task(_reboot_soon())
        return

    await _error(writer, "404 Not Found", "not found")


async def _handle(reader, writer):
    try:
        await _route(reader, writer)
    except Exception as e:
        print("http error:", e)
    try:
        writer.close()
        await writer.wait_closed()
    except Exception:
        pass


async def start(player):
    global _player
    _player = player
    await asyncio.start_server(_handle, "0.0.0.0", config.HTTP_PORT)
    print("http server on port", config.HTTP_PORT)
