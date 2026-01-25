import asyncio
import math
import os
import time
from bleak import BleakClient
from Crypto.Cipher import AES
from PIL import Image


MASK_ADDRESS = "1D:BD:F6:A9:9B:23"

FRAMES_DIR = "frames-video"
FILENAME_TEMPLATE = "out{:05d}.jpg"
START_FRAME = 1
END_FRAME = 6572

WORKING_SLOT_ID = 7

IMG_W = 44
IMG_H = 58

DELAY = 0.05

DISPLAY_CYCLE = 7.0
DISPLAY_CORRECTION = 0.009567

UUID_CMD  = "d44bc439-abfd-45a2-b575-925416129600"
UUID_DATA = "d44bc439-abfd-45a2-b575-92541612960a"

AES_KEY = bytes.fromhex("32672f7974ad43451d9c6c894a0e8764")


def encrypt_cmd(payload: bytes) -> bytes:
    cipher = AES.new(AES_KEY, AES.MODE_ECB)
    return cipher.encrypt(payload.ljust(16, b"\x00")[:16])


def prepare_image(path):
    img = Image.open(path).resize((IMG_W, IMG_H)).convert("RGB")
    px = img.load()

    data = bytearray()
    for x in range(IMG_W):
        for y in range(IMG_H):
            r, g, b = px[x, y]
            data.extend((r, g, b))

    return data


def format_eta(seconds):
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


async def main():
    async with BleakClient(MASK_ADDRESS) as client:
        print("Connected")

        total_frames = END_FRAME - START_FRAME + 1
        frames_done = 0

        dele = b"\x06DELE\x01" + WORKING_SLOT_ID.to_bytes(1, "big")

        # начальная очистка
        await client.write_gatt_char(UUID_CMD, encrypt_cmd(dele), response=True)
        await asyncio.sleep(DELAY)

        for frame in range(START_FRAME, END_FRAME + 1):
            cycle_start = time.time()
            frame_start = cycle_start

            path = os.path.join(FRAMES_DIR, FILENAME_TEMPLATE.format(frame))
            if not os.path.exists(path):
                continue

            img = prepare_image(path)
            img_size = len(img)

            # ---------- DATS ----------
            dats = (
                b"\x09DATS" +
                img_size.to_bytes(2, "big") +
                WORKING_SLOT_ID.to_bytes(2, "big") +
                b"\x01"
            )
            await client.write_gatt_char(UUID_CMD, encrypt_cmd(dats), response=True)
            await asyncio.sleep(DELAY)

            # ---------- DATA ----------
            chunks = math.ceil(img_size / 98)
            for i in range(chunks):
                chunk = img[i * 98:(i + 1) * 98]
                pkt = bytes((len(chunk) + 1, i)) + chunk
                pkt += b"\x00" * (100 - len(pkt))

                await client.write_gatt_char(UUID_DATA, pkt, response=False)
                await asyncio.sleep(DELAY)

            # ---------- DATCP ----------
            ts = int(time.time())
            datcp = b"\x09DATCP" + ts.to_bytes(4, "big")
            await client.write_gatt_char(UUID_CMD, encrypt_cmd(datcp), response=True)
            await asyncio.sleep(DELAY)

            # ---------- PLAY ----------
            play = b"\x06PLAY\x01" + WORKING_SLOT_ID.to_bytes(1, "big")
            await client.write_gatt_char(UUID_CMD, encrypt_cmd(play), response=True)

            # ---------- DELETE ----------
            await client.write_gatt_char(UUID_CMD, encrypt_cmd(dele), response=True)

            # ---------- TIMING ----------
            frame_time = time.time() - frame_start
            cycle_elapsed = time.time() - cycle_start

            sleep_time = DISPLAY_CYCLE - cycle_elapsed - DISPLAY_CORRECTION
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

            frames_done += 1
            eta = (total_frames - frames_done) * DISPLAY_CYCLE
            eta_str = format_eta(eta)


            print(f"FRAME {frame} - OK ({frame_time:.2f}s). ETA: {eta_str}")

        print("""
        
███████╗██╗███╗   ██╗██╗███████╗██╗  ██╗███████╗██████╗ ██╗
██╔════╝██║████╗  ██║██║██╔════╝██║  ██║██╔════╝██╔══██╗██║
█████╗  ██║██╔██╗ ██║██║███████╗███████║█████╗  ██║  ██║██║
██╔══╝  ██║██║╚██╗██║██║╚════██║██╔══██║██╔══╝  ██║  ██║╚═╝
██║     ██║██║ ╚████║██║███████║██║  ██║███████╗██████╔╝██╗
╚═╝     ╚═╝╚═╝  ╚═══╝╚═╝╚══════╝╚═╝  ╚═╝╚══════╝╚═════╝ ╚═╝
        """)
        await asyncio.sleep(21.0)
        print("""
██████╗  █████╗ ██████╗      █████╗ ██████╗ ██████╗ ██╗     ███████╗
██╔══██╗██╔══██╗██╔══██╗    ██╔══██╗██╔══██╗██╔══██╗██║     ██╔════╝
██████╔╝███████║██║  ██║    ███████║██████╔╝██████╔╝██║     █████╗  
██╔══██╗██╔══██║██║  ██║    ██╔══██║██╔═══╝ ██╔═══╝ ██║     ██╔══╝  
██████╔╝██║  ██║██████╔╝    ██║  ██║██║     ██║     ███████╗███████╗
╚═════╝ ╚═╝  ╚═╝╚═════╝     ╚═╝  ╚═╝╚═╝     ╚═╝     ╚══════╝╚══════╝
        """)
# ================== RUN ==================

if __name__ == "__main__":
    asyncio.run(main())


