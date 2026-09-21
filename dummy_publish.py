import json
import threading
import time
import signal
import sys
import paho.mqtt.client as mqtt
from collections import deque
import mqtt_handlers
import settings


def signal_handler(signum, frame):
    signal.signal(signum, signal.SIG_IGN)  # ignore additional signals
    mqttc.disconnect()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
mqttc.on_message = mqtt_handlers.on_message
mqttc.on_connect = mqtt_handlers.on_connect
mqttc.on_publish = mqtt_handlers.on_publish
mqttc.on_subscribe = mqtt_handlers.on_subscribe
mqttc.connect(settings.MQTT_BROKER, 1883, 30)
mqttc.subscribe("head", 0)
# mqttc.publish("camera", json.dumps({"type": "camera", "value": "photo"}))
# mqttc.publish("head", json.dumps({"type": "head_position", "value": 45}))
# mqttc.publish(json.dumps({"type": "head_move", "value": "up"}))
mqttc.publish("touch", json.dumps({"type": "touch", "value": "up"}))
