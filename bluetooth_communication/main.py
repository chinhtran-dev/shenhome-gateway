import asyncio
import json
import os
import time
from bleak import BleakServer

# Custom BLE service & characteristic UUIDs
SERVICE_UUID = "550e8400-e29b-41d4-a716-446655440000"
CHARACTERISTIC_UUID = "6fa459ea-ee8a-3ca4-894e-db77e160355e"

ssid_password_data = None

async def connect_wifi(ssid, password):
    """Use nmcli to connect to Wi-Fi on Raspberry Pi."""
    print(f"Connecting to Wi-Fi: {ssid}")

    # Add or update the Wi-Fi connection
    os.system(f"nmcli device wifi connect '{ssid}' password '{password}'")

    # Wait for the connection to establish
    time.sleep(10)

    # Check Internet connectivity
    response = os.system("ping -c 1 8.8.8.8 > /dev/null 2>&1")
    if response == 0:
        print("Connected to the Internet.")
    else:
        print("Failed to connect to Wi-Fi.")

def on_write(value: bytearray):
    """Callback function triggered when mobile app writes data to BLE characteristic."""
    global ssid_password_data
    data_str = value.decode("utf-8")
    
    try:
        received_data = json.loads(data_str)
        ssid = received_data.get("ssid")
        password = received_data.get("password")
        user_id = received_data.get("userId")

        print(f"Received: SSID={ssid}, Password={password}, UserID={user_id}")
        
        ssid_password_data = (ssid, password)
    except json.JSONDecodeError:
        print("Invalid JSON received.")

async def start_ble_server():
    """Start a BLE GATT server using Bleak."""
    global ssid_password_data
    
    async with BleakServer() as server:
        service = server.add_new_service(SERVICE_UUID)
        characteristic = service.add_new_characteristic(
            CHARACTERISTIC_UUID,
            ["write"],  # Allows writing from mobile app
            on_write
        )
        print(f"BLE server started. Waiting for connection...")

        while True:
            await asyncio.sleep(1)  # Keep the loop running
            if ssid_password_data:
                ssid, password = ssid_password_data
                await connect_wifi(ssid, password)
                ssid_password_data = None  # Reset after handling

if __name__ == "__main__":
    asyncio.run(start_ble_server())
