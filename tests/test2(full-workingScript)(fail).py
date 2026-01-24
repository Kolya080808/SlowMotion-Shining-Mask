import asyncio
import math
import os
from bleak import BleakClient
from Crypto.Cipher import AES
from PIL import Image

MASK_ADDRESS = "1D:BD:F6:A9:9B:23"

FRAMES_DIR = "frames-video"
# Шаблон имени файла (out{i:05d}.jpg превратится в out00001.jpg)
FILENAME_TEMPLATE = "out{:05d}.jpg"

# Диапазон кадров (например, с 1 по 100)
START_FRAME = 1
END_FRAME = 100

# UUID и Ключи
UUID_CMD = "d44bc439-abfd-45a2-b575-925416129600"
UUID_DATA = "d44bc439-abfd-45a2-b575-92541612960a"
UUID_NOTIFY = "d44bc439-abfd-45a2-b575-925416129601"
AES_KEY = b'\x32\x67\x2f\x79\x74\xad\x43\x45\x1d\x9c\x6c\x89\x4a\x0e\x87\x64'
PADDING = b';\x97\xf2\xf3U\xa9r\x13\x8b'

upload_event = asyncio.Event()


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def encrypt_packet(payload):
    cipher = AES.new(AES_KEY, AES.MODE_ECB)
    if len(payload) < 16:
        raw = payload + PADDING[:16 - len(payload)]
    else:
        raw = payload
    return cipher.encrypt(raw)


def prepare_image_bytes(filepath):
    try:
        img = Image.open(filepath)
        # Ресайз до 46x58 (стандарт Shining Mask)
        img = img.resize((46, 58))
        img = img.convert("RGB")
        byte_data = bytearray()
        for r, g, b in list(img.getdata()):
            byte_data.extend([r, g, b])
        return byte_data
    except Exception as e:
        print(f"Ошибка чтения файла {filepath}: {e}")
        return None


def notification_handler(sender, data):
    # Разблокируем ожидание при ответе от маски
    upload_event.set()


async def upload_image(client, image_bytes):
    """Загрузка картинки. Возвращает True, если успешно."""
    size = len(image_bytes)
    # Команда DATS
    cmd = b'\x08DATS' + size.to_bytes(2, 'big') + b'\x00\x00\x00'

    upload_event.clear()
    await client.write_gatt_char(UUID_CMD, encrypt_packet(cmd))

    # Ждем подтверждения готовности к приему
    try:
        await asyncio.wait_for(upload_event.wait(), timeout=3.0)
    except asyncio.TimeoutError:
        print("   ! Нет ответа DATS, но пробую слать данные...")

    # Разбивка на пакеты
    CHUNK_SIZE = 90
    total_chunks = math.ceil(len(image_bytes) / CHUNK_SIZE)

    for i in range(total_chunks):
        chunk = image_bytes[i * CHUNK_SIZE: (i + 1) * CHUNK_SIZE]
        # Header: [Len+1] [Index]
        packet = bytes([len(chunk) + 1, i]) + chunk
        await client.write_gatt_char(UUID_DATA, packet)
        await asyncio.sleep(0.03)  # Небольшая пауза для стабильности

    await asyncio.sleep(0.5)  # Пауза на сохранение во Flash
    return True


async def play_slot(client, slot_id):
    cmd = b'\x06PLAY\x01' + int(slot_id).to_bytes(1, 'big')
    await client.write_gatt_char(UUID_CMD, encrypt_packet(cmd))


async def delete_slot(client, slot_id):
    cmd = b'\x06DELE\x01' + int(slot_id).to_bytes(1, 'big')
    await client.write_gatt_char(UUID_CMD, encrypt_packet(cmd))


# --- ГЛАВНЫЙ ЦИКЛ ---

async def main():
    print(f"Подключение к {MASK_ADDRESS}...")
    async with BleakClient(MASK_ADDRESS) as client:
        print("Подключено!")
        await client.start_notify(UUID_NOTIFY, notification_handler)

        # Мы будем использовать слот #7 (следующий после ваших 6)
        # Мы будем постоянно перезаписывать этот слот или удалять его.
        WORKING_SLOT = 7

        for frame_num in range(START_FRAME, END_FRAME + 1):

            # 1. Формируем имя файла
            filename = FILENAME_TEMPLATE.format(frame_num)
            filepath = os.path.join(FRAMES_DIR, filename)

            print(f"\n--- КАДР {frame_num} ({filename}) ---")

            # 2. Готовим байты
            img_bytes = prepare_image_bytes(filepath)
            if not img_bytes:
                continue  # Пропускаем, если файл битый

            # 3. Загружаем
            print("Загрузка...", end="", flush=True)
            await upload_image(client, img_bytes)
            print(" Готово.")

            # 4. Показываем
            print("Включаю на маске...", end="", flush=True)
            await play_slot(client, WORKING_SLOT)
            print(" Готово.")

            # 5. Ждем вас (СЪЕМКА)
            # Если хотите делать фото автоматически с интервалом, замените input на asyncio.sleep(2)
            input(f" >>> Сделайте фото кадра {frame_num} и нажмите ENTER для продолжения <<< ")

            # 6. Удаляем (чистим место)
            print("Удаляю...", end="", flush=True)
            await delete_slot(client, WORKING_SLOT)
            await asyncio.sleep(0.5)  # Ждем пока маска удалит
            print(" Готово.")

        print("\nСъемка завершена!")


if __name__ == "__main__":
    if MASK_ADDRESS == "YOUR_MASK_ADDRESS_HERE":
        print("ОШИБКА: Впишите адрес маски в код!")
    else:
        asyncio.run(main())