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
START_FRAME = 1
END_FRAME = 100
WORKING_SLOT_ID = 7

IMG_W = 46
IMG_H = 58

UUID_CMD = "d44bc439-abfd-45a2-b575-925416129600"
UUID_NOTIFY = "d44bc439-abfd-45a2-b575-925416129601"
UUID_DATA = "d44bc439-abfd-45a2-b575-92541612960a"

AES_KEY = b'\x32\x67\x2f\x79\x74\xad\x43\x45\x1d\x9c\x6c\x89\x4a\x0e\x87\x64'

# Тот самый магический хвост из main.py, который работал!
MAGIC_PADDING = b';\x97\xf2\xf3U\xa9r\x13\x8b'

evt_dats_ok = asyncio.Event()
evt_reok_ok = asyncio.Event()
evt_datcp_ok = asyncio.Event()


def encrypt_cmd(payload):
    cipher = AES.new(AES_KEY, AES.MODE_ECB)
    # Добиваем магическим паддингом до 16 байт
    if len(payload) < 16:
        # Берем кусок хвоста нужной длины
        tail = MAGIC_PADDING[:16 - len(payload)]
        raw = payload + tail
    else:
        raw = payload[:16]
    return cipher.encrypt(raw)


def prepare_image(filepath):
    try:
        with Image.open(filepath) as img:
            img = img.resize((IMG_W, IMG_H))
            img = img.convert("RGB")
            return img.tobytes()
    except Exception as e:
        print(f"Ошибка файла: {e}")
        return None


def notification_handler(sender, data):
    # Декодируем в HEX и ASCII для отл��дки
    hex_str = data.hex()
    try:
        ascii_str = data.decode('ascii', errors='ignore')
    except:
        ascii_str = "?"

    print(f"   [MASK SAYS]: HEX={hex_str} | ASCII='{ascii_str}'")

    # Проверяем все варианты подтверждения DATS
    # DATSOK (444154534f4b) или DATOK (4441544f4b)
    if "444154534f4b" in hex_str or "4441544f4b" in hex_str:
        print("   -> Подтверждение загрузки получено!")
        evt_dats_ok.set()

    # REOKOK
    elif "52454f4b4f4b" in hex_str:
        evt_reok_ok.set()

    # DATCPOK
    elif "44415443504f4b" in hex_str:
        evt_datcp_ok.set()


async def send_command_dats(client, image_size, slot_id):
    # 4 bytes DATS + 2 size + 2 index + 1 type = 9 args
    # Total len prefix = 9
    cmd_body = b'DATS' + image_size.to_bytes(2, 'big') + slot_id.to_bytes(2, 'big') + b'\x01'
    full_cmd = b'\x09' + cmd_body

    print(f"   [DEBUG] Отправляю DATS: {full_cmd.hex()}")

    evt_dats_ok.clear()
    await client.write_gatt_char(UUID_CMD, encrypt_cmd(full_cmd), response=True)

    try:
        await asyncio.wait_for(evt_dats_ok.wait(), timeout=5.0)
        return True
    except asyncio.TimeoutError:
        print("   !!! TIMEOUT: Маска молчит на DATS.")
        return False


async def send_image_data(client, image_bytes):
    MAX_PAYLOAD = 98
    total_chunks = math.ceil(len(image_bytes) / MAX_PAYLOAD)

    for i in range(total_chunks):
        chunk = image_bytes[i * MAX_PAYLOAD: (i + 1) * MAX_PAYLOAD]

        # Header: Len(chunk)+1 , Index
        header = bytes([len(chunk) + 1, i])
        packet = header + chunk

        # Добиваем нулями до 100 байт (требование протокола)
        if len(packet) < 100:
            packet += b'\x00' * (100 - len(packet))

        evt_reok_ok.clear()
        await client.write_gatt_char(UUID_DATA, packet, response=False)

        # Ждем подтверждения REOKOK
        try:
            await asyncio.wait_for(evt_reok_ok.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            print(f"   ! Пакет {i} без подтверждения REOKOK (но продолжаем)")


async def send_command_datcp(client):
    timestamp = int(time.time())
    cmd_body = b'DATCP' + timestamp.to_bytes(4, 'big')
    full_cmd = b'\x08' + cmd_body

    evt_datcp_ok.clear()
    await client.write_gatt_char(UUID_CMD, encrypt_cmd(full_cmd), response=True)
    try:
        await asyncio.wait_for(evt_datcp_ok.wait(), timeout=3.0)
    except:
        pass


async def send_command_play(client, slot_id):
    cmd = b'\x06PLAY\x01' + slot_id.to_bytes(1, 'big')
    await client.write_gatt_char(UUID_CMD, encrypt_cmd(cmd), response=True)


async def send_command_dele(client, slot_id):
    cmd = b'\x06DELE\x01' + slot_id.to_bytes(1, 'big')
    await client.write_gatt_char(UUID_CMD, encrypt_cmd(cmd), response=True)


async def main():
    print(f"Подключение к {MASK_ADDRESS}...")
    async with BleakClient(MASK_ADDRESS, timeout=20.0) as client:
        print("Подключено!")
        await client.start_notify(UUID_NOTIFY, notification_handler)
        await asyncio.sleep(1.0)

        for frame_num in range(START_FRAME, END_FRAME + 1):
            filename = FILENAME_TEMPLATE.format(frame_num)
            filepath = os.path.join(FRAMES_DIR, filename)

            if not os.path.exists(filepath):
                continue

            print(f"\n=== КАДР {frame_num} ===")
            img_bytes = prepare_image(filepath)

            print("1. DATS...")
            if not await send_command_dats(client, len(img_bytes), WORKING_SLOT_ID):
                print("Сбой DATS. Пропускаю кадр.")
                continue

            print("2. DATA...")
            await send_image_data(client, img_bytes)

            print("3. DATCP...")
            await send_command_datcp(client)

            print("4. PLAY...")
            await send_command_play(client, WORKING_SLOT_ID)

            input(">>> ENTER = ДАЛЬШЕ <<<")

            print("5. DELE...")
            await send_command_dele(client, WORKING_SLOT_ID)
            await asyncio.sleep(1.0)


if __name__ == "__main__":
    asyncio.run(main())