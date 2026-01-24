import asyncio
import math
import os
import time
from bleak import BleakClient
from Crypto.Cipher import AES
from PIL import Image

# --- КОНФИГУРАЦИЯ ---
MASK_ADDRESS = "1D:BD:F6:A9:9B:23"

FRAMES_DIR = "frames-video"
FILENAME_TEMPLATE = "out{:05d}.jpg"
START_FRAME = 100
END_FRAME = 115
WORKING_SLOT_ID = 7

IMG_W = 44
IMG_H = 58

# UUID
UUID_CMD = "d44bc439-abfd-45a2-b575-925416129600"
UUID_DATA = "d44bc439-abfd-45a2-b575-92541612960a"

AES_KEY = b'\x32\x67\x2f\x79\x74\xad\x43\x45\x1d\x9c\x6c\x89\x4a\x0e\x87\x64'


def encrypt_cmd(payload):
    # Точная копия логики из test3 (который работал)
    cipher = AES.new(AES_KEY, AES.MODE_ECB)
    pad_len = 16 - len(payload)
    if pad_len > 0:
        raw = payload + b'\x00' * pad_len
    else:
        raw = payload[:16]
    return cipher.encrypt(raw)


def prepare_image(filepath):
    try:
        with Image.open(filepath) as img:
            img = img.resize((IMG_W, IMG_H))
            img = img.convert("RGB")
            return img.tobytes()
    except:
        return None


async def main():
    print(f"Подключение к {MASK_ADDRESS}...")
    async with BleakClient(MASK_ADDRESS, timeout=20.0) as client:
        print("Подключено! (Blind Mode)")
        await asyncio.sleep(1.0)

        for frame_num in range(START_FRAME, END_FRAME + 1):
            filename = FILENAME_TEMPLATE.format(frame_num)
            filepath = os.path.join(FRAMES_DIR, filename)

            if not os.path.exists(filepath):
                continue

            img_bytes = prepare_image(filepath)
            if not img_bytes: continue

            print(f"\n>>> КАДР {frame_num} <<<")

            # --- 1. DATS (Start) ---
            # Структура из test3: len 0x09 + DATS + size(2) + slot(2) + type(1)
            cmd_body = b'DATS' + len(img_bytes).to_bytes(2, 'big') + WORKING_SLOT_ID.to_bytes(2, 'big') + b'\x01'
            full_cmd = b'\x09' + cmd_body

            print("1. Отправка DATS...", end="")
            await client.write_gatt_char(UUID_CMD, encrypt_cmd(full_cmd), response=True)
            print(" OK. Жду 1 сек...")

            # СЛЕПАЯ ПАУЗА (Верим, что маска готова)
            await asyncio.sleep(1.0)

            # --- 2. DATA (Upload) ---
            print(f"2. Заливка {len(img_bytes)} байт...", end="")
            MAX_PAYLOAD = 98
            total_chunks = math.ceil(len(img_bytes) / MAX_PAYLOAD)

            for i in range(total_chunks):
                chunk = img_bytes[i * MAX_PAYLOAD: (i + 1) * MAX_PAYLOAD]
                # Header: Len+1, Index
                header = bytes([len(chunk) + 1, i])
                packet = header + chunk

                # Padding до 100 байт (важно для последнего пакета)
                if len(packet) < 100:
                    packet += b'\x00' * (100 - len(packet))

                # Шлем без подтверждения, но с паузой
                await client.write_gatt_char(UUID_DATA, packet, response=False)
                await asyncio.sleep(0.05)  # 50мс пауза между пакетами (безопасно)

            print(" Готово.")
            await asyncio.sleep(0.5)  # Пауза перед финализацией

            # --- 3. DATCP (Finish) ---
            print("3. Финализация DATCP...", end="")
            ts = int(time.time())
            cmd_datcp = b'\x08DATCP' + ts.to_bytes(4, 'big')
            await client.write_gatt_char(UUID_CMD, encrypt_cmd(cmd_datcp), response=True)
            print(" OK.")
            await asyncio.sleep(1.0)  # Даем маске сохранить файл

            # --- 4. PLAY ---
            print("4. Включение картинки...", end="")
            cmd_play = b'\x06PLAY\x01' + WORKING_SLOT_ID.to_bytes(1, 'big')
            await client.write_gatt_char(UUID_CMD, encrypt_cmd(cmd_play), response=True)
            print(" OK.")

            # --- 5. DELE ---
            print("5. Удаление...", end="")
            cmd_dele = b'\x06DELE\x01' + WORKING_SLOT_ID.to_bytes(1, 'big')
            await client.write_gatt_char(UUID_CMD, encrypt_cmd(cmd_dele), response=True)
            print(" OK.")
            await asyncio.sleep(1.5)  # Удаление долгое, ждем


if __name__ == "__main__":
    asyncio.run(main())