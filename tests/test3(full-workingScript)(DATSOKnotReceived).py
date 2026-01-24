import asyncio
import math
import os
import time
import struct
from bleak import BleakClient, BleakScanner
from Crypto.Cipher import AES
from PIL import Image

# --- КОНФИГУРАЦИЯ ---
MASK_ADDRESS = "1D:BD:F6:A9:9B:23"  # Ваш адрес из логов

# Папка с кадрами (frames-video/outXXXXX.jpg)
FRAMES_DIR = "frames-video"
FILENAME_TEMPLATE = "out{:05d}.jpg"
START_FRAME = 1
END_FRAME = 100
WORKING_SLOT_ID = 7  # Слот, в который будем писать (перезаписывать)

# Разрешение маски.
# Shining Mask обычно 46x58. Если изображение "сдвинуто" по диагонали, попробуйте 44x58.
IMG_W = 46
IMG_H = 58

# --- UUID и КЛЮЧИ ---
UUID_CMD = "d44bc439-abfd-45a2-b575-925416129600"  # Write (Commands)
UUID_NOTIFY = "d44bc439-abfd-45a2-b575-925416129601"  # Notify (Responses)
UUID_DATA = "d44bc439-abfd-45a2-b575-92541612960a"  # Write (Image Data)

AES_KEY = b'\x32\x67\x2f\x79\x74\xad\x43\x45\x1d\x9c\x6c\x89\x4a\x0e\x87\x64'

# События для синхронизации
evt_dats_ok = asyncio.Event()  # Разрешение на загрузку
evt_reok_ok = asyncio.Event()  # Подтверждение приема пакета
evt_datcp_ok = asyncio.Event()  # Подтверждение завершения загрузки


def encrypt_cmd(payload):
    """Шифрует команду AES-128 ECB с паддингом до 16 байт."""
    cipher = AES.new(AES_KEY, AES.MODE_ECB)
    # Дополняем случайным мусором или нулями до 16 байт
    # В оригинале использовался фиксированный хвост, тут просто нули, это не критично для padding
    pad_len = 16 - len(payload)
    if pad_len > 0:
        raw = payload + b'\x00' * pad_len
    else:
        raw = payload[:16]  # Если вдруг больше
    return cipher.encrypt(raw)


def prepare_image(filepath):
    """Читает изображение и конвертирует в RGB байты (R,G,B, R,G,B...)"""
    try:
        with Image.open(filepath) as img:
            img = img.resize((IMG_W, IMG_H))
            img = img.convert("RGB")
            return img.tobytes()
    except Exception as e:
        print(f"Ошибка чтения {filepath}: {e}")
        return None


def notification_handler(sender, data):
    """Обработка ответов от маски."""
    hex_data = data.hex()

    # DATSOK (44 41 54 53 4f 4b) - Готов к загрузке
    if "444154534f4b" in hex_data:
        # print("DEBUG: DATSOK received")
        evt_dats_ok.set()

    # REOKOK (52 45 4f 4b 4f 4b) - Пакет принят
    elif "52454f4b4f4b" in hex_data:
        # print("DEBUG: REOKOK received")
        evt_reok_ok.set()

    # DATCPOK (44 41 54 43 50 4f 4b) - Загрузка завершена
    elif "44415443504f4b" in hex_data:
        print("DEBUG: DATCPOK received (Upload Finish confirmed)")
        evt_datcp_ok.set()

    # else:
    #    print(f"DEBUG: Unknown notify: {hex_data}")


async def send_command_dats(client, image_size, slot_id):
    """
    Посылает команду DATS (начало загрузки).
    Структура:
    [Len 0x09] [DATS] [Size H][Size L] [Idx H][Idx L] [Type 0x01]
    """
    # 4 bytes DATS + 2 size + 2 index + 1 type = 9 bytes args
    # Prefix length byte = 9

    cmd_body = b'DATS' + image_size.to_bytes(2, 'big') + slot_id.to_bytes(2, 'big') + b'\x01'
    full_cmd = b'\x09' + cmd_body

    evt_dats_ok.clear()
    await client.write_gatt_char(UUID_CMD, encrypt_cmd(full_cmd), response=True)

    try:
        await asyncio.wait_for(evt_dats_ok.wait(), timeout=5.0)
        return True
    except asyncio.TimeoutError:
        print("!!! TIMEOUT: Не пришел ответ DATSOK")
        return False


async def send_image_data(client, image_bytes):
    """
    Отправляет байты изображения чанками.
    Ждет REOKOK после КАЖДОГО пакета (медленно, но надежно).
    """
    # Максимальный размер полезной нагрузки в пакете: 98 байт (т.к. 1 байт длина, 1 байт индекс)
    # Но протокол говорит: "first byte indicates length of image bytes... max size sent is 100 bytes"
    MAX_PAYLOAD = 98

    total_chunks = math.ceil(len(image_bytes) / MAX_PAYLOAD)

    for i in range(total_chunks):
        start = i * MAX_PAYLOAD
        end = start + MAX_PAYLOAD
        chunk = image_bytes[start:end]

        # Формируем заголовок
        # Byte 0: Длина данных (не включая этот байт и индекс). Т.е. просто len(chunk).
        # Byte 1: Индекс пакета (0x00, 0x01...)

        # ВАЖНО: Документация говорит "packet gets padded up to the full 100 bytes".
        # Это критично для последнего пакета.

        payload_len = len(chunk)
        header = bytes([payload_len, i])

        packet = header + chunk

        # Паддинг нулями до 100 байт
        if len(packet) < 100:
            packet += b'\x00' * (100 - len(packet))

        evt_reok_ok.clear()
        # Пишем без response для скорости, но ждем notify
        await client.write_gatt_char(UUID_DATA, packet, response=False)

        # Ждем подтверждения приема пакета
        # Если убрать это ожидание, скорость вырастет, но риск разрыва (OSError) будет 100%
        try:
            await asyncio.wait_for(evt_reok_ok.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            print(f"!!! TIMEOUT: Пакет {i} не подтвержден (REOKOK)")
            # Можно попробовать повторить, но пока просто идем дальше

    return True


async def send_command_datcp(client):
    """Отправляет команду DATCP (конец загрузки) с текущим временем."""
    timestamp = int(time.time())
    # [Len 0x08] [DATCP] [Time 4 bytes]
    cmd_body = b'DATCP' + timestamp.to_bytes(4, 'big')
    full_cmd = b'\x08' + cmd_body

    evt_datcp_ok.clear()
    await client.write_gatt_char(UUID_CMD, encrypt_cmd(full_cmd), response=True)

    try:
        await asyncio.wait_for(evt_datcp_ok.wait(), timeout=5.0)
    except asyncio.TimeoutError:
        print("!!! TIMEOUT: Не пришел ответ DATCPOK")


async def send_command_play(client, slot_id):
    # PLAY + 1 (count) + slot_id
    cmd = b'\x06PLAY\x01' + slot_id.to_bytes(1, 'big')
    await client.write_gatt_char(UUID_CMD, encrypt_cmd(cmd), response=True)


async def send_command_dele(client, slot_id):
    # DELE + 1 (count) + slot_id
    cmd = b'\x06DELE\x01' + slot_id.to_bytes(1, 'big')
    await client.write_gatt_char(UUID_CMD, encrypt_cmd(cmd), response=True)


async def main():
    print(f"Подключение к {MASK_ADDRESS}...")
    async with BleakClient(MASK_ADDRESS, timeout=20.0) as client:
        print("Подключено!")

        # Включаем уведомления
        await client.start_notify(UUID_NOTIFY, notification_handler)
        await asyncio.sleep(1.0)  # Даем время на инициализацию

        for frame_num in range(START_FRAME, END_FRAME + 1):
            filename = FILENAME_TEMPLATE.format(frame_num)
            filepath = os.path.join(FRAMES_DIR, filename)

            if not os.path.exists(filepath):
                print(f"Файл {filename} не найден")
                continue

            print(f"\n=== ОБРАБОТКА КАДРА {frame_num} ({filename}) ===")

            # 1. Подготовка
            img_bytes = prepare_image(filepath)
            if not img_bytes: continue

            # 2. Старт загрузки (DATS)
            print("1. Запрос DATS... ", end="", flush=True)
            if await send_command_dats(client, len(img_bytes), WORKING_SLOT_ID):
                print("OK")
            else:
                print("FAIL")
                break

            # 3. Передача данных
            print("2. Передача данных... ", end="", flush=True)
            await send_image_data(client, img_bytes)
            print("OK")

            # 4. Финализация (DATCP)
            print("3. Финализация DATCP... ", end="", flush=True)
            await send_command_datcp(client)

            # 5. Показ (PLAY)
            print(f"4. Включаем слот {WORKING_SLOT_ID}... ", end="", flush=True)
            await send_command_play(client, WORKING_SLOT_ID)
            print("OK")

            # 6. Пауза для съемки
            input(">>> НАЖМИТЕ ENTER ДЛЯ СЛЕДУЮЩЕГО КАДРА <<<")

            # 7. Удаление (DELE) - чтобы освободить место
            print("5. Удаление... ", end="", flush=True)
            await send_command_dele(client, WORKING_SLOT_ID)
            await asyncio.sleep(1.0)  # Даем время на стирание Flash
            print("OK")


if __name__ == "__main__":
    if "1D:BD" not in MASK_ADDRESS:
        print("ОШИБКА: Проверьте адрес маски")
    else:
        asyncio.run(main())