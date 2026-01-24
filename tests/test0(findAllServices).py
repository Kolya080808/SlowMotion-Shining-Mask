import asyncio
from bleak import BleakClient

ADDRESS = "1D:BD:F6:A9:9B:23"

async def main():
    client = BleakClient(ADDRESS, timeout=15.0)

    try:
        print(f"Подключение к {ADDRESS}...")
        await client.connect()
        print("CONNECTED:", client.is_connected)

        print("\nСервисы и характеристики:")
        for service in client.services:
            print(f"\nSERVICE {service.uuid}")
            for char in service.characteristics:
                props = ", ".join(char.properties)
                print(f"  CHAR {char.uuid} [{props}]")

    finally:
        if client.is_connected:
            await client.disconnect()
            print("\nОтключено")

asyncio.run(main())
