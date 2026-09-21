import json
import threading
from math import sin, cos, pi
from pylx16a.lx16a import *
import time
import signal
import sys
import paho.mqtt.client as mqtt
from collections import deque
import settings


queue = deque(maxlen=2)


def run_loop():
    running = True
    while running:
        if len(queue) > 0:
            message = queue.pop()
            print(message)


queue_checker = threading.Thread(
            target=run_loop,
            args=(),
        )
queue_checker.start()


def handle_mqtt_event(msg):
    print("handle_mqtt_event: ", msg)
    try:
        command = json.loads(msg.payload.decode("utf-8"))
        msg = command
    except:
        print("failed to decode, probably a string already")
    
    queue.appendleft(msg)


def on_connect(mosq, obj, rc, rc2=None):
    # for subscription in SUBSCRIPTIONS:
    mqttc.subscribe("#", 0)
    print("rc: " + str(rc))


def on_message(mosq, obj, msg):
    handle_mqtt_event(msg)


def on_publish(mosq, obj, mid):
    print("mid: " + str(mid))


def on_subscribe(mosq, obj, mid, granted_qos):
    print("Subscribed: " + str(mid) + " " + str(granted_qos))


def on_log(mosq, obj, level, string):
    pass  # print(string)


def signal_handler(signum, frame):
    signal.signal(signum, signal.SIG_IGN)  # ignore additional signals
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)

if __name__ == "__main__":
    mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
    mqttc.on_message = on_message
    mqttc.on_connect = on_connect
    mqttc.on_publish = on_publish
    mqttc.on_subscribe = on_subscribe
    mqttc.connect(settings.MQTT_BROKER, 1883, 30)
    handle_mqtt_event(json.dumps({"type": "head_move", "value": "up"}))
    print("Starting MQTT subscription")
    mqttc.loop_forever()
