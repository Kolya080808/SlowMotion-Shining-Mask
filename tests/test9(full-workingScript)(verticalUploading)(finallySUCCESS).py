import asyncio
import math
import os
import time
from bleak import BleakClient
from Crypto.Cipher import AES
from PIL import Image

# --- НАСТРОЙКИ ---
MASK_ADDRESS = "1D:BD:F6:A9:9B:23"
FRAMES_DIR = "frames-video"
FILENAME_TEMPLATE = "out{:05d}.jpg"
START_FRAME = 100
END_FRAME = 115
WORKING_SLOT_ID = 7

# ГЕОМЕТРИЯ (Подтверждена дампом bfox.py)
IMG_W = 46
IMG_H = 58

UUID_CMD = "d44bc439-abfd-45a2-b575-925416129600"
UUID_DATA = "d44bc439-abfd-45a2-b575-92541612960a"
AES_KEY = b'\x32\x67\x2f\x79\x74\xad\x43\x45\x1d\x9c\x6c\x89\x4a\x0e\x87\x64'


def encrypt_cmd(payload):
    cipher = AES.new(AES_KEY, AES.MODE_ECB)
    pad_len = 16 - len(payload)
    if pad_len > 0:
        raw = payload + b'\x00' * pad_len
    else:
        raw = payload[:16]
    return cipher.encrypt(raw)


def prepare_image_fox_style(filepath):
    try:
        with Image.open(filepath) as img:
            # 1. Ресайз в 46x58
            img = img.resize((IMG_W, IMG_H))
            img = img.convert("RGB")

            # 2. Упаковка ПО СТОЛБЦАМ (Vertical Scan)
            # Дамп bfox.py показывает большие блоки нулей, что характерно для черных столбцов.
            # Значит идем: X=0 (весь Y), X=1 (весь Y)...

            pixels = img.load()
            byte_data = bytearray()

            for x in range(IMG_W):
                for y in range(IMG_H):
                    r, g, b = pixels[x, y]
                    byte_data.extend([r, g, b])

            return byte_data

    except Exception as e:
        print(f"Error: {e}")
        return None


async def main():
    print(f"Подключение (Fox Format: 46x58 Vertical)...")
    async with BleakClient(MASK_ADDRESS, timeout=30.0) as client:
        print("Подключено!")
        await asyncio.sleep(2.0)

        for frame_num in range(START_FRAME, END_FRAME + 1):
            filename = FILENAME_TEMPLATE.format(frame_num)
            filepath = os.path.join(FRAMES_DIR, filename)

            if not os.path.exists(filepath): continue

            img_bytes = prepare_image_fox_style(filepath)
            if not img_bytes: continue

            print(f">>> Кадр {frame_num} (Bytes: {len(img_bytes)}) <<<")

            # 1. DATS
            cmd_dats = b'\x09DATS' + len(img_bytes).to_bytes(2, 'big') + WORKING_SLOT_ID.to_bytes(2, 'big') + b'\x01'
            await client.write_gatt_char(UUID_CMD, encrypt_cmd(cmd_dats), response=True)
            await asyncio.sleep(0.8)

            # 2. DATA
            MAX_PAYLOAD = 98
            total_chunks = math.ceil(len(img_bytes) / MAX_PAYLOAD)

            for i in range(total_chunks):
                chunk = img_bytes[i * MAX_PAYLOAD: (i + 1) * MAX_PAYLOAD]
                packet = bytes([len(chunk) + 1, i]) + chunk
                if len(packet) < 100:
                    packet += b'\x00' * (100 - len(packet))
                await client.write_gatt_char(UUID_DATA, packet, response=False)
                await asyncio.sleep(0.03)

            await asyncio.sleep(0.5)

            # 3. DATCP
            ts = int(time.time())
            cmd_datcp = b'\x08DATCP' + ts.to_bytes(4, 'big')
            await client.write_gatt_char(UUID_CMD, encrypt_cmd(cmd_datcp), response=True)
            await asyncio.sleep(0.8)

            # 4. PLAY
            cmd_play = b'\x06PLAY\x01' + WORKING_SLOT_ID.to_bytes(1, 'big')
            await client.write_gatt_char(UUID_CMD, encrypt_cmd(cmd_play), response=True)
            print("   [ON]")

            await asyncio.sleep(3.0)

            # 5. DELE
            cmd_dele = b'\x06DELE\x01' + WORKING_SLOT_ID.to_bytes(1, 'big')
            await client.write_gatt_char(UUID_CMD, encrypt_cmd(cmd_dele), response=True)
            await asyncio.sleep(1.2)


if __name__ == "__main__":
    asyncio.run(main())