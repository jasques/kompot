import time

from picamera2 import Picamera2
import libcamera
import settings
import arrow
import json
import threading
import signal
import sys
import paho.mqtt.client as mqtt
from collections import deque
import io
from PIL import Image, ImageOps
import mqtt_handlers
from v1_logging import get_logger


logger = get_logger(__name__)
queue = deque(maxlen=2)


class RobotCamera:
    """
        camera module that subscribes to a MQTT topic "camera"
        topic expects a json object with a key "type" and a value of "photo".
        The MQTT on_message method returns a string with a local filesystem path to a photo.
        * {"type": "photo"}
        * {"type": "photo_with_print"}
        * {"type": "constant_preview"}
        """
    
    def __init__(self, queue=None):
        self.queue = queue
        self.thread_queue = deque(maxlen=2)
        self.running = True
        self.preview_running = False
        self.preview_checker = None
        self.picam2 = Picamera2()
    
    def camera_loop(self):
        while self.running:
            time.sleep(0.3)
            if len(self.queue) > 0:
                msg = self.queue.pop()
                if type(msg) == dict:
                    logger.info("Received event", _event=msg)
                    
                    if msg["type"] == "photo":
                        self.preview_running = False
                        self.thread_queue.appendleft("stop")
                        time.sleep(0.5)
                        self.take_photo()
                    
                    if msg["type"] == "constant_preview":
                        self.preview_running = True
                        self.thread_queue.clear()
                        # self.preview_checker = threading.Thread(
                        #     target=self.constant_preview,
                        #     args=(),
                        # )
                        # self.preview_checker.start()
                    
                    if msg["type"] == "stop_preview":
                        self.thread_queue.appendleft("stop")
                        self.preview_running = False
                    
                    if msg["type"] == "photo_with_print":
                        self.preview_running = False
                        self.thread_queue.appendleft("stop")
                        time.sleep(0.5)
                        self.take_photo_with_print()
    
    def take_photo(self, publish_to_screen: bool = True) -> str:
        """
            A tool to take a photo.
            * publish_to_screen: bool controls if a MQTT event is published to show photo
            Returns a path to a taken photo.
        """
        
        config = self.picam2.create_still_configuration()
        self.picam2.configure(config)
        stream = io.BytesIO()
    
        self.picam2.start()
        self.picam2.capture_file(stream, format='jpeg')
        self.picam2.stop()
        # self.picam2.close()
        
        stream.seek(0)
        image = Image.open(stream)
        image = image.rotate(180)
        image.save(settings.TMP_IMAGE_PATH)
        small_image = ImageOps.cover(image, (510, 510)).convert("RGB")
        image.save("/special/last_small.jpg")  # settings.SMALL_TMP_IMAGE_PATH)
        try:
            file_name = f"{settings.NFS_DIRECTORY}/photo_{arrow.utcnow().isoformat()}.jpg"
            image.save(file_name)
        except:
            logger.warning("NFS volume not accessible, skipping")
        
        if publish_to_screen:
            mqttc.publish("screen", json.dumps({"type": "photo", "value": settings.TMP_IMAGE_PATH}))
        return settings.TMP_IMAGE_PATH
    
    def take_photo_with_print(self):
        """
            A tool to take a photo and print it.
            Returns None.
        """
        self.take_photo()
        mqttc.publish("printer", json.dumps({"type": "print", "value": settings.TMP_IMAGE_PATH}))
    
    def constant_preview(self, publish_to_screen: bool = False) -> str:
        """
            A tool to take a photo.
            * publish_to_screen: bool controls if a MQTT event is published to show photo
            Returns a path to a taken photo.
        """
        
        model_h, model_w, _ = 512, 512, 0  # hailo.get_input_shape()
        video_w, video_h = 1280, 960
        main = {'size': (video_w, video_h), 'format': 'XRGB8888'}
        lores = {'size': (model_w, model_h), 'format': 'RGB888'}
        controls = {'FrameRate': 4}
        config = self.picam2.create_preview_configuration(main, lores=lores, controls=controls)
        self.picam2.configure(config)
        self.picam2.set_controls({"AeEnable": True, "AwbEnable": True, "FrameRate": 4.0})
        
        self.picam2.start()
        while self.preview_running:
            if len(self.thread_queue) > 0:
                if self.thread_queue.pop() == "stop":
                    self.preview_running = False
                    break
            
            r = self.picam2.capture_request()
            image = r.make_image("main")
            r.release()
            # stream = io.BytesIO()
            # self.picam2.capture_file(stream, format='jpeg')
            # stream.seek(0)
            # image = Image.open(stream)
            image = ImageOps.cover(image, (model_h, model_w)).convert("RGB")
            image = image.rotate(180)
            image.save(settings.CAM_PREVIEW_PATH)
            time.sleep(0.1)
            if publish_to_screen:
                mqttc.publish("screen", json.dumps({"type": "fast_photo", "value": settings.CAM_PREVIEW_PATH}))
            # stream.close()
        
        self.picam2.stop()
        # self.picam2.close()
        try:
            image = Image.open(settings.CAM_PREVIEW_PATH)
            image.save("/nfs/preview.jpg")
        except:
            logger.warning("There was an issue while saving to NFS volume")
        
        return settings.CAM_PREVIEW_PATH


def on_message(mosq, obj, msg: json):
    try:
        command = json.loads(msg.payload.decode("utf-8"))
        msg = command
    except Exception as e:
        logger.error(f"msg type({type(msg)}): {msg}")
        logger.error(e)
    
    if type(msg) == dict:
        queue.appendleft(msg)


def on_connect(mosq, obj, rc, rc2=None):
    # for subscription in SUBSCRIPTIONS:
    logger.info("Connected.")
    mqttc.subscribe("camera", 0)
    

def signal_handler(signum, frame):
    signal.signal(signum, signal.SIG_IGN)  # ignore additional signals
    camera.running = False
    camera.preview_running = False
    time.sleep(1)
    mqttc.disconnect()
    sys.exit(0)


if __name__ == "__main__":
    mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
    camera = RobotCamera(queue)
    signal.signal(signal.SIGINT, signal_handler)
    
    mqttc.on_message = on_message
    mqttc.on_connect = on_connect
    mqttc.on_publish = mqtt_handlers.on_publish
    mqttc.on_subscribe = mqtt_handlers.on_subscribe
    mqttc.connect(settings.MQTT_BROKER, 1883, 60)
    logger.info("Connecting to MQTT broker...")
    mqttc.loop_start()
    camera.camera_loop()
