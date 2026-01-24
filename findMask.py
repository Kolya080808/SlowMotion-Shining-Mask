import asyncio
from bleak import BleakScanner, BleakClient

AE01_UUID_PART = "ae01"


async def is_mask(name):
    if not name:
        return False
    return name.upper().startswith('MASK')


async def main():
    devices_without_mask = {}
    devices_with_mask = {}

    print("Сканирование при выключенной маске...")
    devices = await BleakScanner.discover(timeout=5.0)
    for d in devices:
        devices_without_mask[d.address] = d.name or ""

    print(f"Найдено устройств: {len(devices_without_mask)}")
    print("\n")
    input("Включите маску и нажмите Enter...")
    print("\n")

    print("Сканирование при включенной маске...")
    devices = await BleakScanner.discover(timeout=5.0)
    for d in devices:
        devices_with_mask[d.address] = d.name or ""

    print(f"Найдено устройств: {len(devices_with_mask)}")
    print("\nКандидаты (устройства, появившиеся после включения маски):")
    candidates = []
    for address, name in devices_with_mask.items():
        if address not in devices_without_mask:
            print(f"  {address} ({name})")
            candidates.append((address, name))

    print(f"\nНайдено кандидатов: {len(candidates)}")

    if not candidates:
        print("❌ Не найдено новых устройств после включения маски")

    print("\nПроверка кандидатов подключением...\n")


    for address, name in candidates:
        print(f"Проверяем устройство: {address} ({name})...")

        if await is_mask(name):
            print("\n==============================")
            print("🎯 НАЙДЕНА МАСКА")
            print(f"Адрес: {address}")
            print(f"Имя: {name}")
            print("==============================")
            return
        else:
            print(f"  ✗ Устройство '{name}' не начинается с MASK")


    print("\nАльтернативная проверка всех устройств из второго сканирования...")
    for address, name in devices_with_mask.items():
        print(f"Проверяем: {address} ({name})...")
        if await is_mask(name):
            print("\n==============================")
            print("🎯 НАЙДЕНА МАСКА (в общем списке)")
            print(f"Адрес: {address}")
            print(f"Имя: {name}")
            print("==============================")
            return

    print("\n❌ Маска не найдена")


if __name__ == "__main__":
    asyncio.run(main())


asyncio.run(main())