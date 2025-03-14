import os
import time
import json
from subprocess import Popen, PIPE
import bluetooth

def run_bluetoothctl_command(command):
    """Runs a bluetoothctl command and returns output"""
    process = Popen(["bluetoothctl"], stdin=PIPE, stdout=PIPE, stderr=PIPE, text=True)
    process.stdin.write(command + "\n")
    process.stdin.close()
    output, _ = process.communicate()
    return output

def connect_wifi(ssid, password):
    """Connects to Wi-Fi using nmcli on Raspberry Pi"""
    print(f"Connecting to Wi-Fi: {ssid}")
    os.system(f"nmcli device wifi connect '{ssid}' password '{password}'")
    time.sleep(5)
    response = os.system("ping -c 1 8.8.8.8 > /dev/null 2>&1")
    if response == 0:
        print("Successfully connected to Wi-Fi.")
    else:
        print("Wi-Fi connection failed.")

def start_bluetooth_server():
    """Starts an RFCOMM Bluetooth server to receive credentials"""
    run_bluetoothctl_command("discoverable on")
    run_bluetoothctl_command("pairable on")

    server_socket = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
    server_socket.bind(("", bluetooth.PORT_ANY))
    server_socket.listen(1)
    port = server_socket.getsockname()[1]

    print(f"Waiting for connection on RFCOMM channel {port}...")

    client_socket, client_info = server_socket.accept()
    print(f"Connected to {client_info}")

    try:
        data = client_socket.recv(1024).decode().strip()
        if data:
            print(f"Received: {data}")
            try:
                received_data = json.loads(data)
                ssid = received_data.get("ssid")
                password = received_data.get("password")
                user_id = received_data.get("userId")

                print(f"SSID: {ssid}, Password: {password}, UserID: {user_id}")

                client_socket.send("Data received.".encode())
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
