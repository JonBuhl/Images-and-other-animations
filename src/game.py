import uasyncio
import random

from image import Image


def val(buffer, x, y):
    #if (x >= 16 or x < 0 or y >= 16 or y < 0):
    #    return 0
    
    return buffer.get(x % 16, y % 16)


async def next_gen_rnd(current, target):
    current.clear()
    target.clear()
    img = Image().get()
    for i in range(0, 16):
        for j in range(0, 16):
            target.set(i, j, img[i][j]) 
    await uasyncio.sleep(0)


async def next_gen_snowfall(current, target):
    target.clear()
    for i in range(0, 16):
        target.set(0, i, random.randint(0,1))
    for j in range(1, 16):
        for k in range(0, 16):
            target.set(j, k, val(target, j-1, k))
            #print(val(current, j-1, k))
    await uasyncio.sleep(0)


async def next_gen_game_of_life(current, target):
    target.clear()
    for i in range(0, 16):
        for j in range(0, 16):
            total = val(current, i-1, j-1) + val(current, i, j-1) + val(current, i+1, j-1) + val(current, i-1, j) + val(current, i+1, j) + val(current, i-1, j+1) + val(current, i, j+1) + val(current, i+1, j+1)
            if current.get(i, j):
                if (total < 2) or (total > 3):
                    target.set(i, j, 0)
                else:
                    target.set(i, j, 1)
            else:
                if total == 3:
                    target.set(i, j, 1)
                else:
                    target.set(i, j, 0)
        await uasyncio.sleep(0)
