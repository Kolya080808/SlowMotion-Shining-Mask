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

    print("Scanning with turned off mask...")
    devices = await BleakScanner.discover(timeout=5.0)
    for d in devices:
        devices_without_mask[d.address] = d.name or ""

    print(f"Found devices: {len(devices_without_mask)}")
    print("\n")
    input("Turn on the mask and press Enter...")
    print("\n")

    print("Scanning with turned on mask...")
    devices = await BleakScanner.discover(timeout=5.0)
    for d in devices:
        devices_with_mask[d.address] = d.name or ""

    print(f"Found devices: {len(devices_with_mask)}")
    print("\nCandidates:")
    candidates = []
    for address, name in devices_with_mask.items():
        if address not in devices_without_mask:
            print(f"  {address} ({name})")
            candidates.append((address, name))

    print(f"\Found candidates: {len(candidates)}")

    if not candidates:
        print("❌ Not found.")

    print("\nChecking with names...\n")


    for address, name in candidates:
        print(f"Cheking candidate: {address} ({name})...")

        if await is_mask(name):
            print("\n==============================")
            print("🎯 FOUND MASK!!")
            print(f"Address: {address}")
            print(f"Name: {name}")
            print("==============================")
            return
        else:
            print(f"  ✗ Device '{name}' does not start with MASK")


    print("\nAlternative check...")
    for address, name in devices_with_mask.items():
        print(f"Checking: {address} ({name})...")
        if await is_mask(name):
            print("\n==============================")
            print("🎯 FOUND MAK!! (in general list)")
            print(f"Address: {address}")
            print(f"Name: {name}")
            print("==============================")
            return

    print("\n❌ Not found.")


if __name__ == "__main__":
    asyncio.run(main())


asyncio.run(main())