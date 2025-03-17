import json
import os
import requests
import netifaces
from paho.mqtt import client as mqtt

MQTT_BROKER = os.getenv("MQTT_BROKER")
MQTT_PORT = int(os.getenv("MQTT_PORT", 8883))
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")
NODE_RED_URL = "http://localhost:1880"
NODE_RED_GROUP = "Automations"
NODE_RED_USERNAME = os.getenv("NODERED_USERNAME")
NODE_RED_PASSWORD = os.getenv("NODERED_PASSWORD")

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

        mac = mac.lower()
        return mac
    except Exception as e:
        print(f"Error getting gateway MAC: {e}")
        raise Exception("Failed to retrieve a valid gateway MAC address")
    
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
        
        time_triggers = [t for t in payload["triggers"] if t["type"] == "time"]
        if len(time_triggers) > 1:
            print("Error: Only one time trigger is allowed")
            return
        
        create_node_red_flow(payload, gateway_mac)
    except Exception as e:
        print(f"Error processing message: {e}")
        
def get_mqtt_config(access_token):
    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}"
        }
        tabs_response = requests.get(f"{NODE_RED_URL}/flows", headers=headers)
        if tabs_response.status_code == 200:
            flows = tabs_response.json()
            node_red_tab = next(
                (f["id"] for f in flows if "type" in f and f["type"] == "mqtt-broker" and "label" in f and f["name"] == "mosquitto"),
                "main_tab"
            )            
            return node_red_tab
        else:
            print(f"Failed to get tabs: {tabs_response.status_code} - {tabs_response.text}")
            return "main_tab"
    except Exception as e:
        print(f"Error getting Node-RED tabs: {e}")
        return "main_tab"
        
def create_node_red_flow(automation, gateway_mac):
    nodes = []
    
    auth_payload = {
        "client_id": "node-red-editor",
        "grant_type": "password",
        "scope": "*",
        "username": NODE_RED_USERNAME,
        "password": NODE_RED_PASSWORD
    }

    token_response = requests.post(f"{NODE_RED_URL}/auth/token", json=auth_payload)
    if token_response.status_code != 200:
        print(f"Failed to get access token: {token_response.status_code} - {token_response.text}")
        return

    access_token = token_response.json().get("access_token")
    
    # 1. cron-plus for time trigger
    time_trigger = next((t for t in automation["triggers"] if t["type"] == 2), None)
    if time_trigger:
        
        options = [
            {
                "name": f"schedule{i+1}",
                "topic": f"topic{i+1}",
                "payloadType": "boolean",
                "payload": True,
                "expressionType": "cron",
                "expression": expr,
            }
            for i, expr in enumerate(time_trigger["expression"])
        ]
        
        nodes.append({
            "id": f"cron_{automation['id']}",
            "type": "cronplus",
            "z": automation["id"],
            "name": f"Cron {automation['name']}",
            "timeZone": "Asia/Ho_Chi_Minh",
            "commandResponseMsgOutput": "output1",
            "outputs": 1,
            "options": options,
            "wires": [[f"logic_{automation['id']}"]],
            "env": {}
        })

    # 2. mqtt-in for each device trigger
    device_triggers = [t for t in automation["triggers"] if t["type"] == 1]
    mqtt_ins = []
    for i, trigger in enumerate(device_triggers):
        mqtt_node_id = f"mqtt_in_{automation['id']}_{i}"
        mqtt_ins.append({
            "id": mqtt_node_id,
            "type": "mqtt in",
            "z": automation["id"],
            "name": f"MQTT {trigger['mac']}",
            "topic": trigger["mac"],
            "qos": "0",
            "datatype": "auto",
            "broker": "mosquitto",
            "wires": [[f"logic_{automation['id']}"]],
            "env": {}
        })


    # Logic node
    nodes.append({
        "id": f"logic_{automation['id']}",
        "type": "function",
        "z": automation["id"],
        "name": f"Logic {automation['name']}",
        "func": generate_logic_function(automation),
        "outputs": len(automation["actions"]),
        "noerr": 0,
        "wires": [[f"out_{automation['id']}_{i}" for i in range(len(automation["actions"]))]],
        "env": {}
    })

    # 5. MQTT Out
    device_actions = [action for action in automation["actions"] if action["type"] == 0]
    out_nodes = []
    for i, action in enumerate(device_actions):
        out_nodes.append({
            "id": f"out_{automation['id']}_{i}",
            "type": "mqtt out",
            "z": automation["id"],
            "name": f"MQTT Out {automation['name']}",
            "topic": f"device/{action['mac']}/command",
            "qos": "0",
            "contentType": "application/json",
            "retain": "",
            "broker": "mosquitto",
            "wires": [],
            "env": {}
        })

    
    mqtt_config_id = get_mqtt_config(access_token)
    
    configs = [
        {
            "id": mqtt_config_id,
            "type": "mqtt-broker",
            "name": "mosquitto",
            "broker": "mosquitto",
            "port": 1883,
        }
    ]

    # Create flow for the automation
    flow_config = {
        "id": automation["id"],
        "label": NODE_RED_GROUP,
        "nodes": nodes + mqtt_ins,
        "configs": configs,
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
        
    response = requests.post(f"{NODE_RED_URL}/flow", json=flow_config, headers=headers)

    if response.status_code == 200:
        print("Flow created successfully")
    else:
        print(f"Failed to create flow: {response.status_code} - {response.text}")

def generate_logic_function(automation):
    automation_json = json.dumps(automation)
    func = """
// Save trigger state to global context
const deviceTriggers = {};
const automation = AUTOMATION_JSON;

// Handle device trigger (type == 1)
if (msg.topic && automation.triggers.some(t => t.type === 1 && t.mac === msg.topic)) {
    const trigger = automation.triggers.find(t => t.type === 1 && t.mac === msg.topic);
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

    global.set("deviceTrigger_" + automation.id + "_" + trigger.mac, {
        satisfied: deviceTriggerSatisfied,
        timestamp: Date.now()
    });
    return null;
}

// Handle time trigger from cron-plus (type == 2)
if (automation.isOnce && global.get("executed_" + automation.id)) {
    return null;
}

const timeTriggerSatisfied = automation.triggers.some(t => t.type === 2); // Cron đã kích hoạt
let deviceTriggersSatisfied = [];

automation.triggers.forEach(trigger => {
    if (trigger.type === 1) {
        const state = global.get("deviceTrigger_" + automation.id + "_" + trigger.mac) || { satisfied: false };
        const timeout = 5 * 60 * 1000; // 5 phút
        if (Date.now() - (state.timestamp || 0) > timeout) {
            global.set("deviceTrigger_" + automation.id + "_" + trigger.mac, { satisfied: false, timestamp: Date.now() });
            deviceTriggersSatisfied.push(false);
        } else {
            deviceTriggersSatisfied.push(state.satisfied);
        }
    }
});

// Logic dựa trên isMatchAll
let allTriggersSatisfied;
if (automation.isMatchAll === false) {
    allTriggersSatisfied = timeTriggerSatisfied || (deviceTriggersSatisfied.length > 0 && deviceTriggersSatisfied.some(s => s));
} else {
    allTriggersSatisfied = timeTriggerSatisfied && deviceTriggersSatisfied.every(s => s);
}

if (allTriggersSatisfied) {
    const messages = automation.actions.map(action => {
        const payloadObj = {};
        payloadObj[action.property] = action.value;
        return {
            topic: "device/" + action.mac + "/command",
            payload: JSON.stringify(payloadObj)
        };
    });
    if (automation.isOnce) {
        global.set("executed_" + automation.id, true);
    }
    return messages;
}
return null;
""".replace("AUTOMATION_JSON", automation_json)
    return func

if __name__ == "__main__":
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.tls_set()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_BROKER, MQTT_PORT)
    client.loop_forever()