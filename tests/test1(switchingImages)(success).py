import asyncio
from bleak import BleakClient
from Crypto.Cipher import AES

# --- НАСТРОЙКИ ---
# ВАЖНО: Вставьте сюда адрес вашей маски
# Windows/Linux: MAC-адрес вида "AA:BB:CC:11:22:33"
# macOS: UUID устройства вида "XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX"
MASK_ADDRESS = "1D:BD:F6:A9:9B:23"

CHARACTERISTIC_UUID = "d44bc439-abfd-45a2-b575-925416129600"

# Ключ и паддинг (из main.py)
AES_KEY = b'\x32\x67\x2f\x79\x74\xad\x43\x45\x1d\x9c\x6c\x89\x4a\x0e\x87\x64'
PADDING = b';\x97\xf2\xf3U\xa9r\x13\x8b'


def build_play_packet(image_id):
    """Создает зашифрованную команду PLAY для картинки с номером image_id"""
    # \x06 - длина, PLAY - команда, \x01 - кол-во картинок
    prefix = b'\x06PLAY\x01'
    img_byte = (image_id % 256).to_bytes(1, 'big')
    raw = prefix + img_byte + PADDING

    cipher = AES.new(AES_KEY, AES.MODE_ECB)
    return cipher.encrypt(raw)


async def main():
    print(f"Попытка прямого подключения к {MASK_ADDRESS}...")

    try:
        async with BleakClient(MASK_ADDRESS) as client:
            print(f"Подключено! Проверяю соединение: {client.is_connected}")

            # Перебираем слоты. Обычно слотов не больше 20-30.
            # Если ваши картинки не появляются, попробуйте поменять range на (100, 150)
            print("Начинаю переключение изображений...")

            for i in range(1, 7):
                print(f"--> Отправляю команду: Показать картинку #{i}")
                packet = build_play_packet(i)

                try:
                    await client.write_gatt_char(CHARACTERISTIC_UUID, packet)
                except Exception as e:
                    print(f"Ошибка записи в характеристику: {e}")

                # Задержка, чтобы успеть увидеть результат
                await asyncio.sleep(2.0)

            print("Тест завершен.")

    except Exception as e:
        print(f"Не удалось подключиться: {e}")
        print("Проверьте адрес и убедитесь, что маска не подключена к телефону в данный момент.")


if __name__ == "__main__":
    if MASK_ADDRESS == "YOUR_MASK_ADDRESS_HERE":
        print("ОШИБКА: Вы забыли вписать адрес маски в переменную MASK_ADDRESS в начале скрипта!")
    else:
        asyncio.run(main())