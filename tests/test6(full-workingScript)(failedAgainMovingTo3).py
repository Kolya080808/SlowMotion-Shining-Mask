import asyncio
import math
import os
import time
from bleak import BleakClient
from Crypto.Cipher import AES
from PIL import Image

MASK_ADDRESS = "1D:BD:F6:A9:9B:23"
AES_KEY = b'\x32\x67\x2f\x79\x74\xad\x43\x45\x1d\x9c\x6c\x89\x4a\x0e\x87\x64'

# UUID
UUID_CMD = "d44bc439-abfd-45a2-b575-925416129600"
UUID_NOTIFY = "d44bc439-abfd-45a2-b575-925416129601"
UUID_DATA = "d44bc439-abfd-45a2-b575-92541612960a"

# Разрешение
IMG_W = 46
IMG_H = 58

# Папка с кадрами
FRAMES_DIR = "frames-video"
FILENAME_TEMPLATE = "out{:05d}.jpg"
START_FRAME = 1
END_FRAME = 100
WORKING_SLOT_ID = 7

evt_dats_ok = asyncio.Event()


def encrypt_cmd_zeros(payload):
    """Шифруем с паддингом НУЛЯМИ (как в test3)"""
    cipher = AES.new(AES_KEY, AES.MODE_ECB)
    pad_len = 16 - len(payload)
    if pad_len > 0:
        raw = payload + b'\x00' * pad_len
    else:
        raw = payload[:16]
    return cipher.encrypt(raw)


def decrypt_data(encrypted_payload):
    try:
        cipher = AES.new(AES_KEY, AES.MODE_ECB)
        return cipher.decrypt(encrypted_payload)
    except:
        return b''


def notification_handler(sender, data):
    decrypted = decrypt_data(data)
    hex_str = decrypted.hex()

    print(f"   [MASK]: RAW={data.hex()[:6]}.. | DECRYPT={hex_str}")

    # Ищем DATSOK / DATOK
    if "444154534f4b" in hex_str or "4441544f4b" in hex_str:
        print("   -> (!!!) DATSOK ПОЛУЧЕН")
        evt_dats_ok.set()


def prepare_image(filepath):
    try:
        with Image.open(filepath) as img:
            img = img.resize((IMG_W, IMG_H))
            img = img.convert("RGB")
            return img.tobytes()
    except:
        return None


async def send_command_dats(client, image_size, slot_id):
    # Возвращаемся к структуре из Test3 (которая вызывала гифку)
    # DATS (4) + Size (2) + Slot (2) + Type (1) = 9 байт данных
    # Но попробуем префикс длины 0x08 (вдруг маска не считает Type?)

    # ВАРИАНТ А: Как в test3 (почти)
    cmd_body = b'DATS' + image_size.to_bytes(2, 'big') + slot_id.to_bytes(2, 'big') + b'\x01'
    full_cmd = b'\x09' + cmd_body  # Честные 9 байт

    print(f"   [TX] DATS... ({full_cmd.hex()})")

    evt_dats_ok.clear()
    await client.write_gatt_char(UUID_CMD, encrypt_cmd_zeros(full_cmd), response=True)

    try:
        await asyncio.wait_for(evt_dats_ok.wait(), timeout=5.0)
        return True
    except asyncio.TimeoutError:
        print("   !!! TIMEOUT: Маска молчит.")
        return False


async def main():
    print(f"Подключение к {MASK_ADDRESS}...")
    async with BleakClient(MASK_ADDRESS, timeout=20.0) as client:
        print("Подключено!")
        await client.start_notify(UUID_NOTIFY, notification_handler)
        await asyncio.sleep(2.0)

        # Берем только первый кадр для теста
        filename = FILENAME_TEMPLATE.format(1)
        filepath = os.path.join(FRAMES_DIR, filename)
        img_bytes = prepare_image(filepath)

        if img_bytes:
            print("\n=== ТЕСТ DATS (как в test3) ===")
            if await send_command_dats(client, len(img_bytes), WORKING_SLOT_ID):
                print("УРА! ПОЛУЧИЛОСЬ!")
            else:
                print("Не вышло.")


if __name__ == "__main__":
    asyncio.run(main())