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

# Разрешение
IMG_W = 46
IMG_H = 58

# UUID
UUID_CMD = "d44bc439-abfd-45a2-b575-925416129600"
UUID_NOTIFY = "d44bc439-abfd-45a2-b575-925416129601"  # Сюда приходят зашифрованные ответы
UUID_DATA = "d44bc439-abfd-45a2-b575-92541612960a"

AES_KEY = b'\x32\x67\x2f\x79\x74\xad\x43\x45\x1d\x9c\x6c\x89\x4a\x0e\x87\x64'
MAGIC_PADDING = b';\x97\xf2\xf3U\xa9r\x13\x8b'

evt_dats_ok = asyncio.Event()
evt_reok_ok = asyncio.Event()
evt_datcp_ok = asyncio.Event()


def encrypt_data(payload):
    """Шифрование исходящих команд"""
    cipher = AES.new(AES_KEY, AES.MODE_ECB)
    if len(payload) < 16:
        tail = MAGIC_PADDING[:16 - len(payload)]
        raw = payload + tail
    else:
        raw = payload[:16]
    return cipher.encrypt(raw)


def decrypt_data(encrypted_payload):
    """Дешифровка входящих ответов"""
    try:
        cipher = AES.new(AES_KEY, AES.MODE_ECB)
        decrypted = cipher.decrypt(encrypted_payload)
        return decrypted
    except Exception as e:
        print(f"Ошибка дешифровки: {e}")
        return b''


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
    # 1. Сначала расшифровываем то, что пришло
    decrypted = decrypt_data(data)
    hex_str = decrypted.hex()

    # Пытаемся получить ASCII для чтения глазами
    try:
        # Убираем паддинг и мусор, оставляем только читаемые символы для лога
        ascii_str = "".join([chr(b) if 32 <= b <= 126 else "." for b in decrypted])
    except:
        ascii_str = "?"

    print(f"   [MASK]: RAW={data.hex()[:8]}... | DECRYPT={hex_str} | TXT='{ascii_str}'")

    # 2. Ищем ключевые слова в расшифрованном тексте
    # DATSOK (444154534f4b) или DATOK
    if "444154534f4b" in hex_str or "4441544f4b" in hex_str:
        print("   -> (!!!) DATSOK ПОЛУЧЕН")
        evt_dats_ok.set()

    # REOKOK (52454f4b4f4b)
    elif "52454f4b4f4b" in hex_str:
        evt_reok_ok.set()

    # DATCPOK (44415443504f4b)
    elif "44415443504f4b" in hex_str:
        print("   -> (!!!) DATCPOK ПОЛУЧЕН")
        evt_datcp_ok.set()


async def send_command_dats(client, image_size, slot_id):
    # Команда DATS: 09 + DATS + Size(2) + Slot(2) + Type(1)
    cmd_body = b'DATS' + image_size.to_bytes(2, 'big') + slot_id.to_bytes(2, 'big') + b'\x01'
    full_cmd = b'\x09' + cmd_body

    print(f"   [TX] DATS... ({full_cmd.hex()})")

    evt_dats_ok.clear()
    await client.write_gatt_char(UUID_CMD, encrypt_data(full_cmd), response=True)

    try:
        # Ждем 5 секунд
        await asyncio.wait_for(evt_dats_ok.wait(), timeout=5.0)
        return True
    except asyncio.TimeoutError:
        print("   !!! TIMEOUT: Маска не ответила DATSOK.")
        return False


async def send_image_data(client, image_bytes):
    MAX_PAYLOAD = 98
    total_chunks = math.ceil(len(image_bytes) / MAX_PAYLOAD)

    print(f"   [TX] Отправка {total_chunks} пакетов...")

    for i in range(total_chunks):
        chunk = image_bytes[i * MAX_PAYLOAD: (i + 1) * MAX_PAYLOAD]
        header = bytes([len(chunk) + 1, i])
        packet = header + chunk

        if len(packet) < 100:
            packet += b'\x00' * (100 - len(packet))

        evt_reok_ok.clear()

        # ВАЖНО: UUID_DATA НЕ ШИФРУЕТСЯ (по документации)
        await client.write_gatt_char(UUID_DATA, packet, response=False)

        try:
            await asyncio.wait_for(evt_reok_ok.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            # Не паникуем, просто идем дальше, иногда REOKOK теряется
            # print(f"   ! Нет REOKOK на пакет {i}")
            pass

    return True


async def send_command_datcp(client):
    timestamp = int(time.time())
    cmd_body = b'DATCP' + timestamp.to_bytes(4, 'big')
    full_cmd = b'\x08' + cmd_body

    print("   [TX] DATCP...")
    evt_datcp_ok.clear()
    await client.write_gatt_char(UUID_CMD, encrypt_data(full_cmd), response=True)
    try:
        await asyncio.wait_for(evt_datcp_ok.wait(), timeout=3.0)
    except:
        pass


async def send_command_play(client, slot_id):
    cmd = b'\x06PLAY\x01' + slot_id.to_bytes(1, 'big')
    await client.write_gatt_char(UUID_CMD, encrypt_data(cmd), response=True)


async def send_command_dele(client, slot_id):
    cmd = b'\x06DELE\x01' + slot_id.to_bytes(1, 'big')
    await client.write_gatt_char(UUID_CMD, encrypt_data(cmd), response=True)


async def main():
    print(f"Подключение к {MASK_ADDRESS}...")

    # Увеличил таймаут подключения до 30 сек
    async with BleakClient(MASK_ADDRESS, timeout=30.0) as client:
        print("Подключено!")
        await client.start_notify(UUID_NOTIFY, notification_handler)
        await asyncio.sleep(2.0)  # Хорошая пауза на старт

        for frame_num in range(START_FRAME, END_FRAME + 1):
            filename = FILENAME_TEMPLATE.format(frame_num)
            filepath = os.path.join(FRAMES_DIR, filename)

            if not os.path.exists(filepath):
                continue

            print(f"\n=== КАДР {frame_num} ===")
            img_bytes = prepare_image(filepath)

            # 1. DATS
            if not await send_command_dats(client, len(img_bytes), WORKING_SLOT_ID):
                print("Сбой DATS. Жду 5 сек и пробую следующий кадр...")
                await asyncio.sleep(5.0)  # Даем маске прийти в себя
                continue

            # Пауза перед передачей данных (на всякий случай)
            await asyncio.sleep(0.2)

            # 2. DATA
            await send_image_data(client, img_bytes)

            # 3. DATCP
            await send_command_datcp(client)

            # 4. PLAY
            print("   [TX] PLAY")
            await send_command_play(client, WORKING_SLOT_ID)

            input(">>> ENTER = ДАЛЬШЕ <<<")

            # 5. DELE
            print("   [TX] DELE")
            await send_command_dele(client, WORKING_SLOT_ID)

            # Большая пауза между кадрами (отдых маске)
            print("   (Ожидание 2 сек...)")
            await asyncio.sleep(2.0)


if __name__ == "__main__":
    asyncio.run(main())