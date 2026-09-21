import settings
import signal
import sys
import paho.mqtt.client as mqtt
from collections import deque
import mqtt_handlers
import json
import subprocess
from v1_logging import get_logger


logger = get_logger(__name__)
queue = deque(maxlen=2)

"""
Interface module that is responsible for the thermal printer.
It subscribes to MQTT topic "print". It expects a json object with:
* {"message_type": "photo", "value": photo_url}
* {"message_type": "text", "value": text}
* {"message_type": "qr", "value": url}
"""


def on_message(mosq, obj, msg: json):
    try:
        command = json.loads(msg.payload.decode("utf-8"))
        msg = command
    except Exception as e:
        logger.error(f"msg type({type(msg)}): {msg}")
        logger.error(e)
    
    if type(msg) == dict:
        if msg["type"] == "halt":
            logger.info("Got halt message - shutting down system")
            subprocess.run("sleep 2 & sudo halt", shell=True)
        
        if msg["type"] == "update-system":
            logger.info("Got request to update system")
            subprocess.run("cd /home/pi/kompot && git pull; sudo supervisorctl restart all", shell=True)


def on_connect(mosq, obj, rc, rc2=None):
    # for subscription in SUBSCRIPTIONS:
    logger.info("Connected.")
    mqttc.subscribe("system", 0)


def signal_handler(signum, frame):
    signal.signal(signum, signal.SIG_IGN)  # ignore additional signals
    p.close()
    mqttc.disconnect()
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    logger.info("Created system instance")
    mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
    mqttc.on_message = on_message
    mqttc.on_connect = on_connect
    mqttc.on_publish = mqtt_handlers.on_publish
    mqttc.on_subscribe = mqtt_handlers.on_subscribe
    mqttc.connect(settings.MQTT_BROKER, 1883, 60)
    logger.info("Connecting to MQTT broker...")
    mqttc.loop_forever()
