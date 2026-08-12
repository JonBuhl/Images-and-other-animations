"""Persistence for uploaded animations.

File format (`/anim/<name>.anm`), all integers little endian:

    offset  size  content
    0       4     magic "FRK1"
    4       1     format version (1)
    5       1     flags (reserved, 0)
    6       2     frame count
    8       2     default frame delay in ms (informational)
    10      2     reserved
    12      ...   frame records

Each frame record is 34 bytes: 2 bytes delay in ms, followed by 32 bytes of
pixel data in the same MONO_VLSB layout the panel uses.
"""

import os

import config

ANIM_DIR = "/anim"
MAGIC = b"FRK1"
HEADER_SIZE = 12
FRAME_SIZE = 34


def ensure_dir():
    try:
        os.mkdir(ANIM_DIR)
    except OSError:
        pass


def sanitize(name):
    """Reduce a user supplied name to something safe as a file name."""
    if not name:
        return None
    out = "".join(c for c in name if c.isalpha() or c.isdigit() or c in "-_. ")
    out = out.strip().replace(" ", "_")
    # no directory parts survive this, and no leading dots either so that
    # nothing can collide with the internal ".upload" file
    out = out.lstrip(".")[:24].rstrip(".")
    if not out:
        return None
    return out


def path_for(name):
    return ANIM_DIR + "/" + name + ".anm"


def exists(name):
    try:
        os.stat(path_for(name))
        return True
    except OSError:
        return False


def _count_from_header(h):
    if len(h) < HEADER_SIZE or h[0:4] != MAGIC:
        return -1
    return h[6] | (h[7] << 8)


def validate(path):
    """Return the frame count of a file, or -1 if it is not a usable animation."""
    try:
        size = os.stat(path)[6]
        with open(path, "rb") as f:
            header = f.read(HEADER_SIZE)
    except OSError:
        return -1
    count = _count_from_header(header)
    if count <= 0 or count > config.MAX_FRAMES:
        return -1
    if size != HEADER_SIZE + count * FRAME_SIZE:
        return -1
    return count


def list_animations():
    result = []
    try:
        names = os.listdir(ANIM_DIR)
    except OSError:
        return result
    for fn in names:
        if not fn.endswith(".anm"):
            continue
        path = ANIM_DIR + "/" + fn
        count = validate(path)
        if count < 0:
            continue
        result.append({"name": fn[:-4], "frames": count, "size": os.stat(path)[6]})
    result.sort(key=lambda a: a["name"])
    return result


def delete(name):
    try:
        os.remove(path_for(name))
        return True
    except OSError:
        return False


def free_space():
    try:
        s = os.statvfs("/")
        return s[0] * s[3]
    except OSError:
        return 0
