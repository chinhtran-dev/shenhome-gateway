import bluetooth
import json
import os
import time

def connect_wifi(ssid, password):
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

def start_bluetooth_server():
    """Start a Bluetooth server to receive SSID and Password from a phone."""
    server_socket = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
    server_socket.bind(("", bluetooth.PORT_ANY))
    server_socket.listen(1)

    port = server_socket.getsockname()[1]
    bluetooth.advertise_service(server_socket, "SSIDPassServer",
                                service_classes=[bluetooth.SERIAL_PORT_CLASS],
                                profiles=[bluetooth.SERIAL_PORT_PROFILE])

    print(f"Waiting for connection on RFCOMM channel {port}...")

    client_socket, client_info = server_socket.accept()
    print(f"Connected to {client_info}")

    try:
        while True:
            data = client_socket.recv(1024).decode().strip()
            if not data:
                break
            
            print(f"Received: {data}")

            # Parse JSON data
            try:
                received_data = json.loads(data)
                ssid = received_data.get("ssid")
                password = received_data.get("password")
                user_id = received_data.get("userId")

                print(f"SSID: {ssid}, Password: {password}, UserID: {user_id}")

                # Send acknowledgment to the phone
                client_socket.send("Data received.".encode())

                # Connect to Wi-Fi
                connect_wifi(ssid, password)

            except json.JSONDecodeError:
                print("Invalid JSON received.")
                client_socket.send("Invalid JSON format.".encode())

    except Exception as e:
        print(f"Error: {e}")

    finally:
        print("Closing connection...")
        client_socket.close()
        server_socket.close()

if __name__ == "__main__":
    start_bluetooth_server()
