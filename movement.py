import arrow
import json
import threading
from math import sin, cos, pi
from pylx16a.lx16a import *
import time
import signal
import sys
import paho.mqtt.client as mqtt
import mqtt_handlers
from collections import deque
from adafruit_servokit import ServoKit
import settings
from v1_logging import get_logger


logger = get_logger(__name__)
LX16A.initialize(settings.LX_BUS_PORT)
UP = "up"
DOWN = "down"
queue = deque(maxlen=3)


"""
Interface module that is responsible for the head movement.
It subscribes to MQTT topic "head". It expects a json object with:
* {"type": "head_move", "value": "up", "msec": optional_ms_movement_time}
* {"type": "head_move", "value": "down", "msec": optional_ms_movement_time}
* {"type": "head_position", "value": numeric_angle, "msec": optional_ms_movement_time}

Angle has to be between 5.1 and 104.9 degrees.
The head has to be parked before cycling power.
"""


class Movement:
    def __init__(self):
        self.last_message_ts = arrow.utcnow()
        try:
            self.servo1 = LX16A(1, disable_torque=False)
            # servo2 = LX16A(2)
            self.servo1.set_angle_limits(5, 105)
            # servo2.set_angle_limits(0, 240)
        except ServoTimeoutError as e:
            logger.info(f"Servo {e.id_} is not responding. Exiting...")
            quit()
        
        self.t = 0.05
        try:
            self.kit = ServoKit(channels=16)
            self.kit.servo[15].angle = 0
            self.antenna = self.kit.servo[15]
        except:
            logger.error("Failure in servo driver init")
            self.kit = None
            self.antenna = None
        
        self.direction = UP
        self.running = True
        self.wiggle_start = None
        
    def stop(self):
        self.running = False

    def move_up(self, msec: int = 2500):
        try:
            self.t = 104
            self.servo1.move(self.t, msec)
            # logger.info("t: ", t)
        except:
            logger.info(f"Incorrect angle {self.t}")
    
    def move_down(self, msec: int = 2000):
        try:
            self.t = 5.5
            self.servo1.move(self.t, msec)
            # logger.info("t: ", t)
        except:
            logger.info(f"Incorrect angle {self.t}")
    
    def move_to_position(self, new_t: float = 0.05, msec: int = 1000):
        logger.info(f"Moving to position: {self.direction}, t: {self.t}, new_t: {new_t}, ms: {msec}")
        try:
            self.servo1.move(new_t, msec)
            self.t = new_t
        except:
            logger.info(f"Incorrect angle {new_t}")
    
    def wiggle_antenna(self, seconds: int = 1):
        if not self.wiggle_start:
            self.wiggle_start = arrow.utcnow()
        
        left = True
        sleep_time = 0.1
        for i in range(0, int(seconds/sleep_time)):
            if left:
                self.antenna.angle = 90
                time.sleep(sleep_time)
                left = False
                continue
            self.antenna.angle = 130
            time.sleep(sleep_time)
            left = True
        
        self.wiggle_start = None
        self.antenna.angle = 110
    
    def hide_antenna(self, seconds: int = 3):
        sleep_time = 0.05
        start_angle = self.antenna.angle
        steps = int(seconds / sleep_time)
        angle_delta = int(start_angle/steps)
        for i in range(0, steps):
            self.antenna.angle = self.antenna.angle - angle_delta
            time.sleep(sleep_time)
    
    def run_loop(self):
        time.sleep(0.5)
        loop_sleep_s = 0.25
        while self.running:
            time.sleep(loop_sleep_s)
            if(arrow.utcnow() - self.last_message_ts).total_seconds() > 4:
                self.servo1.disable_torque()
            
            if len(queue) > 0:
                self.servo1.enable_torque()
                message = queue.pop()
                logger.info("New item in queue, checking type")
                logger.info(f"message[type]: {message['type']}")
                self.last_message_ts = arrow.utcnow()
                
                if message["type"] == "wiggle_antenna":
                    logger.info("Confirm: antenna wiggle")
                    self.wiggle_antenna(seconds=message.get("seconds", 1))
                    continue
                
                if message["type"] == "hide_antenna":
                    logger.info("Confirm: hide antenna")
                    self.hide_antenna(seconds=message.get("seconds", 3))
                    continue
                
                if message["type"] == "head_position":
                    logger.info("Confirm: head_position")
                    self.move_to_position(new_t=message["value"], msec=message.get("msec", 1000))
                    continue
                
                if message["type"] == "head_move":
                    logger.info("Confirm: head_move")
                    if message.get("delay", 0) > 0:
                        message["delay"] = message["delay"] - loop_sleep_s * 1000
                        queue.appendleft(message)
                        continue
                    
                    if message["value"] == "up":
                        self.move_up()
                    if message["value"] == "down":
                        self.move_down()

                    
movement = Movement()
queue_checker = threading.Thread(
            target=movement.run_loop,
            args=(),
        )
queue_checker.start()


def on_message(mosq, obj, msg):
    try:
        command = json.loads(msg.payload.decode("utf-8"))
        msg = command
    except Exception as e:
        logger.info(f"ERROR: msg type = {type(msg)}: {msg}")
        logger.info(e)
    
    if type(msg) == dict:
        logger.info("Received event", _event=msg)
        queue.appendleft(msg)


def on_connect(mosq, obj, rc, rc2=None):
    logger.info("Connected.")
    mqttc.subscribe("head", 0)


def signal_handler(signum, frame):
    logger.info("Lowering head - please wait...")
    queue.appendleft({"type": "head_move", "value": "down"})
    time.sleep(2.2)
    signal.signal(signum, signal.SIG_IGN)  # ignore additional signals
    movement.stop()
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
    mqttc.on_message = on_message
    mqttc.on_connect = on_connect
    mqttc.on_publish = mqtt_handlers.on_publish
    mqttc.on_subscribe = mqtt_handlers.on_subscribe
    mqttc.connect(settings.MQTT_BROKER, 1883, 60)
    logger.info("Connecting to MQTT broker...")
    mqttc.loop_forever()
