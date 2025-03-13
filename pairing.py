import paho.mqtt.client as mqtt
import socket
import json
import subprocess

# MQTT Configuration
MQTT_BROKER = "5bcd2ba05ac244df97c50e24839cfb61.s1.eu.hivemq.cloud"
MQTT_TOPIC_PAIRING = "pairing"
MQTT_TOPIC_REGISTER = "register"

# UDP Configuration
UDP_IP = "255.255.255.255"
UDP_PORT = 8888

def get_wifi_credentials():
    """Fetch SSID and password from wpa_supplicant.conf"""
    ssid = "UnknownSSID"
    password = "UnknownPassword"
    
    try:
        with open("/etc/wpa_supplicant/wpa_supplicant.conf", "r") as f:
            lines = f.readlines()
            for i in range(len(lines)):
                if "ssid" in lines[i]:
                    ssid = lines[i].split("=")[1].strip().replace('"', '')
                if "psk" in lines[i]:
                    password = lines[i].split("=")[1].strip().replace('"', '')
    except Exception as e:
        print(f"Error retrieving Wi-Fi credentials: {e}")
    
    return ssid, password

def get_ip_address():
    """Retrieve the current IP address of Raspberry Pi"""
    try:
        result = subprocess.check_output("hostname -I", shell=True)
        ip_address = result.decode().strip().split()[0]  # Get first available IP
    except Exception as e:
        print(f"Error retrieving IP: {e}")
        ip_address = "192.168.1.100"  # Default fallback IP
    
    return ip_address

def on_message(client, userdata, message):
    payload = json.loads(message.payload.decode())
    print(f"Received MQTT from HiveMQ: {payload}")

    if message.topic == MQTT_TOPIC_PAIRING:
        # Get dynamic SSID, Password, and Raspberry Pi IP
        ssid, password = get_wifi_credentials()
        pi_ip = get_ip_address()

        # Send UDP Broadcast
        udp_data = json.dumps({"ssid": ssid, "password": password, "pi_ip": pi_ip})
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        udp_socket.sendto(udp_data.encode(), (UDP_IP, UDP_PORT))
        print(f"📡 Sent UDP Broadcast! SSID: {ssid}, IP: {pi_ip}")

    elif message.topic == MQTT_TOPIC_REGISTER:
        device_mac = payload.get("mac")
        device_type = payload.get("type")
        print(f"ESP32 Registered: MAC={device_mac}, TYPE={device_type}")

client = mqtt.Client()
client.on_message = on_message
client.connect(MQTT_BROKER, 1883)
client.subscribe([(MQTT_TOPIC_PAIRING, 0), (MQTT_TOPIC_REGISTER, 0)])
client.loop_forever()
