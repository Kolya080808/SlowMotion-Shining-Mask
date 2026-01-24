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

# Размеры
IMG_W = 44  # Ширина маски
IMG_H = 58  # Высота маски (попробуем засунуть полную высоту в "текст")

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


def prepare_text_bitmap(filepath):
    try:
        with Image.open(filepath) as img:
            # 1. Ресайз до 44x58
            img = img.resize((IMG_W, IMG_H))
            # 2. Конвертируем в ч/б (1 бит на пиксель)
            # Порог 128: если светлее серого -> 1 (горит), иначе 0
            img = img.convert("1")

            # --- ФОРМИРОВАНИЕ BITMAP ---
            # Документация не говорит про порядок бит, но обычно это строки.
            # Нам нужно упаковать пиксели в байты.
            # Ширина 44 не делится на 8 нацело. Обычно делается паддинг до байта.
            # 44 бита = 5.5 байт -> 6 байт на строку.

            pixels = img.load()
            bitmap_bytes = bytearray()

            # Идем по колонкам (так часто в LED дисплеях) или по строкам?
            # Попробуем классику: По строкам, слева направо.

            # НО! Автор пишет про Text: "Bitmap 16 pixels high... width 44".
            # Значит скорее всего формат: [Колонка 1 (16 бит)], [Колонка 2]...
            # Если высота 58, то это [Колонка 1 (58 бит = 8 байт)], [Колонка 2]...

            # Давайте попробуем вертикальную упаковку (т.к. текст бежит горизонтально)
            # Для каждой колонки X (0..43):
            #   Берем 58 пикселей сверху вниз.
            #   Упаковываем в байты.

            for x in range(IMG_W):
                col_bits = 0
                for y in range(IMG_H):
                    if pixels[x, y] > 0:  # Если белый
                        col_bits |= (1 << y)  # Ставим бит

                # Упаковываем это огромное число (58 бит) в байты
                # 58 бит = 8 байт (7.25)
                # Порядок байт: Little Endian?
                num_bytes = math.ceil(IMG_H / 8)
                col_data = col_bits.to_bytes(num_bytes, 'little')
                bitmap_bytes.extend(col_data)

            return bitmap_bytes

    except Exception as e:
        print(f"Error: {e}")
        return None


async def main():
    print(f"Подключение (TEXT HACK MODE)...")
    async with BleakClient(MASK_ADDRESS, timeout=30.0) as client:
        print("Подключено!")
        await asyncio.sleep(2.0)

        for frame_num in range(START_FRAME, END_FRAME + 1):
            filename = FILENAME_TEMPLATE.format(frame_num)
            filepath = os.path.join(FRAMES_DIR, filename)
            if not os.path.exists(filepath): continue

            bitmap = prepare_text_bitmap(filepath)
            if not bitmap: continue

            print(f">>> Кадр {frame_num} (Bitmap size: {len(bitmap)}) <<<")

            # --- ПОДГОТОВКА ЦВЕТОВ ---
            # Документация: "color array... RGB 0-f... one color per pixel stripe"
            # Нам нужно покрасить все 44 колонки в белый (0xFFF ? Или 0xFFFFFF?)
            # "format RGB 0-f accordingly" -> скорее всего 3 байта на колонку, но значения 0-15?
            # Или 12 бит (4R 4G 4B)?
            # Попробуем просто забить нулями (белый по дефолту?) или FF.

            # Автор пишет: "combined data = bitmap + color array"
            # Если цветов нет, будет белый.
            # Попробуем отправить ТОЛЬКО bitmap, без цветов.

            full_payload = bitmap  # + colors (пока без них)

            bitmap_size = len(bitmap)
            total_size = len(full_payload)

            # 1. DATS (TYPE = 0x00 for Bitmap!)
            # args: [Total Size (2)] [Bitmap Size (2)]
            # Внимание: тут структура аргументов другая, чем для Image!
            # Image: DATS + Size(2) + Index(2) + Type(1)
            # Text:  DATS + TotalSize(2) + BitmapSize(2) + Type(00)?? Нет, в доке сказано:
            # "DATS command with indicator byte set to 0x00... first two bytes size of combined... next two bytes size of bitmap"

            # Структура DATS для Текста:
            # 4 байта 'DATS'
            # 2 байта Total Size
            # 2 байта Bitmap Size
            # 1 байт Indicator (0x00)

            cmd_dats = b'\x09DATS' + total_size.to_bytes(2, 'big') + bitmap_size.to_bytes(2, 'big') + b'\x00'

            await client.write_gatt_char(UUID_CMD, encrypt_cmd(cmd_dats), response=True)
            await asyncio.sleep(0.5)

            # 2. DATA
            MAX_PAYLOAD = 98
            total_chunks = math.ceil(total_size / MAX_PAYLOAD)

            for i in range(total_chunks):
                chunk = full_payload[i * MAX_PAYLOAD: (i + 1) * MAX_PAYLOAD]
                packet = bytes([len(chunk) + 1, i]) + chunk
                if len(packet) < 100:
                    packet += b'\x00' * (100 - len(packet))
                await client.write_gatt_char(UUID_DATA, packet, response=False)
                await asyncio.sleep(0.02)  # Очень быстро, данных мало

            await asyncio.sleep(0.2)

            # 3. DATCP
            ts = int(time.time())
            cmd_datcp = b'\x08DATCP' + ts.to_bytes(4, 'big')
            await client.write_gatt_char(UUID_CMD, encrypt_cmd(cmd_datcp), response=True)
            await asyncio.sleep(0.5)

            # 4. PLAY? Нет, для текста своя команда?
            # Документация молчит, как ВКЛЮЧИТЬ загруженный текст.
            # Скорее всего он начинает отображаться сразу после DATCP?
            # Или используется команда MODE?
            # Попробуем ничего не слать, посмотрим загорится ли.

            print("   [Загружено]")
            await asyncio.sleep(3.0)

            # Для текста нет DELE? Он перезаписывается.


if __name__ == "__main__":
    asyncio.run(main())