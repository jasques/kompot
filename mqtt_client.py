import paho.mqtt.client as mqtt
import mqtt_handlers
from collections import deque
import settings
import json


def on_message(mosq, obj, msg):
    try:
        command = json.loads(msg.payload.decode("utf-8"))
        msg = command
    except Exception as e:
        print(f"ERROR: msg type = {type(msg)}: {msg}")
        print(e)
    
    if type(msg) == dict:
        queue.appendleft(msg)


def on_connect(mosq, obj, rc, rc2=None):
    mqttc.subscribe("screen", 0)


def publish():
    pass


mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
mqttc.on_message = mqtt_handlers.on_message
mqttc.on_connect = mqtt_handlers.on_connect
mqttc.on_publish = mqtt_handlers.on_publish
mqttc.on_subscribe = mqtt_handlers.on_subscribe
mqttc.connect(settings.MQTT_BROKER, 1883, 30)
# run loop in a separate thread

if __name__ == "__main__":
    mqttc.loop_forever()
