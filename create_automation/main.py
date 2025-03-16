import json
import requests
import netifaces
from paho.mqtt import client as mqtt
import time

MQTT_BROKER = "localhost"
MQTT_PORT = 1883
NODE_RED_URL = "http://localhost:1880"
NODE_RED_GROUP = "Automations"

def get_gateway_mac():
    """Gets the MAC address of the default gateway"""
    try:
        interfaces = netifaces.interfaces()
        if not interfaces:
            raise Exception("No network interfaces found")

        target_interface = "eth0" if "eth0" in interfaces else "wlan0" if "wlan0" in interfaces else interfaces[0]
        
        mac = netifaces.ifaddresses(target_interface)[netifaces.AF_LINK][0]["addr"]
        if not mac or mac.lower() == "00:00:00:00:00:00":
            raise Exception(f"Invalid MAC address for interface {target_interface}")

        mac = mac.replace(":", "").lower()
        return mac
    except Exception as e:
        print(f"Error getting gateway MAC: {e}")
        raise Exception("Failed to retrieve a valid gateway MAC address")

def get_node_red_tab():
    try:
        tabs_response = requests.get(f"{NODE_RED_URL}/flows", headers={"Content-Type": "application/json"})
        if tabs_response.status_code == 200:
            flows = tabs_response.json()
            node_red_tab = next((f["id"] for f in flows if "type" in f and f["type"] == "tab"), "main_tab")
            return node_red_tab
        else:
            print(f"Failed to get tabs: {tabs_response.status_code} - {tabs_response.text}")
            return "main_tab"
    except Exception as e:
        print(f"Error getting Node-RED tabs: {e}")
        return "main_tab"
    
def on_connect(client, userdata, flags, rc, properties):
    try:
        print(f"Connected to MQTT broker with code {rc}")
        gateway_mac = get_gateway_mac()
        client.subscribe(f"gateway/{gateway_mac}/create_automation")
        print(f"Subscribed to topic: gateway/{gateway_mac}/create_automation")
    except Exception as e:
        print(f"Failed to subscribe: {e}")
        client.loop_stop()
        client.disconnect()
        
def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        print(f"Received payload: {json.dumps(payload, indent=2)}")
        
        gateway_mac = get_gateway_mac()
        node_red_tab = get_node_red_tab()
        
        time_triggers = [t for t in payload["triggers"] if t["type"] == "time"]
        if len(time_triggers) > 1:
            print("Error: Only one time trigger is allowed")
            return
        
        create_node_red_flow(payload, gateway_mac, node_red_tab)
    except Exception as e:
        print(f"Error processing message: {e}")
        
def create_node_red_flow(automation, gateway_mac, node_red_tab):
    nodes = []

    # 1. cron-plus for time trigger
    time_trigger = next((t for t in automation["triggers"] if t["type"] == "time"), None)
    if time_trigger:
        nodes.append({
            "id": f"cron_{automation['id']}",
            "type": "cron-plus",
            "z": node_red_tab,
            "name": f"Cron {automation['name']}",
            "outputAsObject": False,
            "schedule": time_trigger["value"],
            "x": 100,
            "y": 100,
            "wires": [[f"logic_{automation['id']}"]]
        })

    # 2. mqtt-in for each device trigger
    device_triggers = [t for t in automation["triggers"] if t["type"] == "device"]
    mqtt_nodes = []
    for i, trigger in enumerate(device_triggers):
        mqtt_node_id = f"mqtt_in_{automation['id']}_{i}"
        mqtt_nodes.append({
            "id": mqtt_node_id,
            "type": "mqtt in",
            "z": node_red_tab,
            "name": f"MQTT {trigger['device_mac']}",
            "topic": trigger["device_mac"],
            "qos": "0",
            "datatype": "auto",
            "broker": "mosquitto_broker",
            "x": 100,
            "y": 150 + i * 50,
            "wires": [[f"logic_{automation['id']}"]]
        })


    # 4. Function for handle logic AND/OR
    nodes.append({
        "id": f"logic_{automation['id']}",
        "type": "function",
        "z": node_red_tab,
        "name": f"Logic {automation['name']}",
        "func": generate_logic_function(automation),
        "outputs": len(automation["actions"]),
        "noerr": 0,
        "x": 400,
        "y": 100,
        "wires": [[f"mqtt_out_{automation['id']}" for _ in automation["actions"]]]
    })

    # 5. MQTT Out
    nodes.append({
        "id": f"mqtt_out_{automation['id']}",
        "type": "mqtt out",
        "z": node_red_tab,
        "name": f"MQTT Out {automation['name']}",
        "topic": "",
        "qos": "0",
        "retain": "",
        "broker": "mosquitto_broker",
        "x": 600,
        "y": 100,
        "wires": []
    })

    # Create flow for the automation
    flow_config = {
        "flows": nodes + mqtt_nodes,
        "group": {
            "id": "group_automations",
            "name": NODE_RED_GROUP,
            "type": "group",
            "z": node_red_tab,
            "nodes": [node["id"] for node in nodes + mqtt_nodes]
        }
    }

    # Send request to Node-RED API
    headers = {"Content-Type": "application/json"}
    response = requests.post(f"{NODE_RED_URL}/flows", json=flow_config, headers=headers)
    if response.status_code == 200:
        print(f"Flow for {automation['id']} created successfully for gateway {gateway_mac}")
    else:
        print(f"Failed to create flow: {response.status_code} - {response.text}")

def generate_logic_function(automation):
    func = """
// Save trigger state to global context
const deviceTriggers = {};
const automation = {automation_json};

// Handle device trigger
if (msg.topic && automation.triggers.some(t => t.type === "device" && t.device_mac === msg.topic)) {
    const trigger = automation.triggers.find(t => t.type === "device" && t.device_mac === msg.topic);
    const deviceData = msg.payload;
    if (!deviceData || !deviceData[trigger.field]) return null;

    const deviceValue = deviceData[trigger.field];
    const conditionValue = parseFloat(trigger.value);
    let deviceTriggerSatisfied = false;

    switch (trigger.condition) {
        case ">": deviceTriggerSatisfied = deviceValue > conditionValue; break;
        case "<": deviceTriggerSatisfied = deviceValue < conditionValue; break;
        case "=": deviceTriggerSatisfied = deviceValue == conditionValue; break;
        default: deviceTriggerSatisfied = false;
    }

    global.set(`deviceTrigger_${automation.id}_${trigger.device_mac}`, {
        satisfied: deviceTriggerSatisfied,
        timestamp: Date.now()
    });
    return null;
}

// Handle time trigger from cron-plus
if (automation.isOnce && global.get(`executed_${automation.id}`)) {
    return null;
}

const timeTriggerSatisfied = automation.triggers.some(t => t.type === "time"); // Cron đã kích hoạt
let deviceTriggersSatisfied = [];

automation.triggers.forEach(trigger => {
    if (trigger.type === "device") {
        const state = global.get(`deviceTrigger_${automation.id}_${trigger.device_mac}`) || { satisfied: false };
        const timeout = 5 * 60 * 1000; // 5 phút
        if (Date.now() - (state.timestamp || 0) > timeout) {
            global.set(`deviceTrigger_${automation.id}_${trigger.device_mac}`, { satisfied: false, timestamp: Date.now() });
            deviceTriggersSatisfied.push(false);
        } else {
            deviceTriggersSatisfied.push(state.satisfied);
        }
    }
});

let allTriggersSatisfied = false;
if (automation.logic === "AND") {
    allTriggersSatisfied = timeTriggerSatisfied && deviceTriggersSatisfied.every(s => s);
} else if (automation.logic === "OR") {
    allTriggersSatisfied = timeTriggerSatisfied || deviceTriggersSatisfied.some(s => s);
}

if (allTriggersSatisfied) {
    const messages = automation.actions.map(action => ({
        topic: "device/" + action.device_mac + "/command",
        payload: action.command
    }));
    if (automation.isOnce) {
        global.set(`executed_${automation.id}`, true);
    }
    return messages;
}
return null;
""".format(automation_json=json.dumps(automation))
    return func

if __name__ == "__main__":
    # Initialize MQTT client
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    # Connect to MQTT broker
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_forever()
        print("Listening on dynamic topics (gateway/{gateway_mac}/create_automation)")
    except Exception as e:
        print(f"Failed to connect to MQTT broker: {e}")
        client.loop_stop()
        client.disconnect()