import asyncio


def val(buffer, x, y):
    # the field wraps around, the box is a torus
    return buffer.pixel(x % 16, y % 16)


async def next_gen(current, target):
    target.clear()
    for i in range(0, 16):
        for j in range(0, 16):
            total = (val(current, i - 1, j - 1) + val(current, i, j - 1) + val(current, i + 1, j - 1)
                     + val(current, i - 1, j) + val(current, i + 1, j)
                     + val(current, i - 1, j + 1) + val(current, i, j + 1) + val(current, i + 1, j + 1))
            if current.pixel(i, j):
                target.pixel(i, j, 0 if (total < 2) or (total > 3) else 1)
            else:
                target.pixel(i, j, 1 if total == 3 else 0)
        await asyncio.sleep(0)
