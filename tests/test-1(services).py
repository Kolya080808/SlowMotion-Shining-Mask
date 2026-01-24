import asyncio
from bleak import BleakClient

ADDRESS = "1D:BD:F6:A9:9B:23"

NOTIF_CHARS = [
    "d44bc439-abfd-45a2-b575-925416129601",  # FFF0 notify
    "0000fd02-0000-1000-8000-00805f9b34fb",  # FD00 notify
    "0000ae02-0000-1000-8000-00805f9b34fb",  # AE00 notify
]

def on_notify(uuid):
    def handler(sender, data):
        print(f"[NOTIFY {uuid}] {data.hex()}")
    return handler

async def main():
    client = BleakClient(ADDRESS, timeout=15)
    await client.connect()
    print("CONNECTED")

    for uuid in NOTIF_CHARS:
        try:
            await client.start_notify(uuid, on_notify(uuid))
            print(f"Subscribed {uuid}")
        except Exception as e:
            print(f"Failed subscribe {uuid}: {e}")

    print("Ждём 10 секунд. Ничего не трогаем.")
    await asyncio.sleep(10)

    await client.disconnect()
    print("DISCONNECTED")

asyncio.run(main())

