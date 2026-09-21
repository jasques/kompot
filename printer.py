from escpos.printer import Usb
import settings
import signal
import sys
import paho.mqtt.client as mqtt
from collections import deque
import io
from PIL import Image, ImageOps, ImageEnhance
import mqtt_handlers
import arrow
import json
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


class Printer:
    MAX_HEIGHT = 406
    
    def __init__(self):
        self.p = Usb(0x28e9, 0x0289, 0, profile="TM-T88III", in_ep=0x81, out_ep=0x03)

    def text(self, message):
        self.p.text(f"{message}\n")
        
    def qr(self, url):
        self.p.qr(f"{url}")
    
    def image(self, url: str, fit: bool = True, enhance: bool = True):
        '''
        * `bitImageRaster`: prints with the `GS v 0`-command
        * `graphics`: prints with the `GS ( L`-command
        * `bitImageColumn`: prints with the `ESC *`-command
        '''
        
        try:
            image = Image.open(url)
        except:
            logger.info(f"Error opening image url: '{url}'")
            return
        
        if image.width > image.height:
            image = image.rotate(90, resample=Image.Resampling.BILINEAR, expand=True)
        
        if fit:
            image = ImageOps.cover(image, (self.MAX_HEIGHT, self.MAX_HEIGHT)).convert("RGB")
        
        if enhance:
            image = ImageOps.grayscale(image)
            image = ImageOps.equalize(image)
            image = ImageEnhance.Brightness(image).enhance(1.6)
            # image = ImageEnhance.Contrast(image).enhance(1.5)
        
        file_name = f"{settings.NFS_DIRECTORY}/printer_{arrow.utcnow().isoformat()}.jpg"
        image.save(file_name)
        self.p.image(image, impl="bitImageRaster")
        self.p.cut()

    def close(self):
        self.p.close()


def on_message(mosq, obj, msg: json):
    try:
        command = json.loads(msg.payload.decode("utf-8"))
        msg = command
    except Exception as e:
        logger.error(f"msg type = {type(msg)}: {msg}")
        logger.error(e)
    
    if type(msg) == dict:
        logger.info("Received event", _event=msg)
        
        if msg["type"] == "print":
            if msg.get("value"):
                p.image(msg["value"])
                return
            p.image("/special/last.jpg")


def on_connect(mosq, obj, rc, rc2=None):
    # for subscription in SUBSCRIPTIONS:
    logger.info("Connected.")
    mqttc.subscribe("printer", 0)


def signal_handler(signum, frame):
    signal.signal(signum, signal.SIG_IGN)  # ignore additional signals
    p.close()
    mqttc.disconnect()
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    p = Printer()
    logger.info("Created printer instance")
    mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
    mqttc.on_message = on_message
    mqttc.on_connect = on_connect
    mqttc.on_publish = mqtt_handlers.on_publish
    mqttc.on_subscribe = mqtt_handlers.on_subscribe
    mqttc.connect(settings.MQTT_BROKER, 1883, 60)
    logger.info("Connecting to MQTT broker...")
    mqttc.loop_forever()
