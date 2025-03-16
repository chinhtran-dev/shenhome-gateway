import os
import socket
import json
import subprocess
import paho.mqtt.client as mqtt

# MQTT Configuration
MQTT_BROKER = os.getenv("MQTT_BROKER", "default-broker")
MQTT_PORT = int(os.getenv("MQTT_PORT", 8883))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "default-user")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "default-password")
MQTT_TOPIC_PAIRING = "shenhome/pairing"

# UDP Configuration
UDP_IP = "255.255.255.255"
UDP_PORT = 8888

def get_wifi_credentials():
    """Fetch SSID and password from network manager."""
    try:
        ssid = subprocess.check_output("iwgetid -r", shell=True).decode().strip()
        cmd = f"sudo nmcli -s -g 802-11-wireless-security.psk connection show {ssid}"
        password = subprocess.check_output(cmd, shell=True).decode().strip()
        return ssid, password
    except Exception:
        return "UnknownSSID", "UnknownPassword"

def get_ip_address():
    """Retrieve the current IP address."""
    try:
        return subprocess.check_output("hostname -I", shell=True).decode().strip().split()[0]
    except Exception:
        return "UnknownIP"

def on_connect(client, userdata, flags, reason_code, properties):
    """Callback when connected to MQTT broker."""
    if reason_code == 0:
        print("Connected to HiveMQ Cloud!")
        client.subscribe([(MQTT_TOPIC_PAIRING, 0)])
    else:
        print(f"Failed to connect, reason: {reason_code}")

def on_message(client, userdata, message):
    payload = json.loads(message.payload.decode())
    print(f"Received MQTT message: {payload}")

    if message.topic == MQTT_TOPIC_PAIRING:
        ssid, password = get_wifi_credentials()
        pi_ip = get_ip_address()
        udp_data = json.dumps({"ssid": ssid, "password": password, "ip": pi_ip})
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        udp_socket.sendto(udp_data.encode(), (UDP_IP, UDP_PORT))
        print(f"Sent UDP Broadcast: SSID={ssid}, IP={pi_ip}")


# MQTT Client Setup
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
client.tls_set()
client.on_connect = on_connect
client.on_message = on_message
client.connect(MQTT_BROKER, MQTT_PORT)
client.loop_forever()