import arrow
import json
import threading
from pydualsense import *
import lirc
import time
import signal
import sys
import paho.mqtt.client as mqtt
import mqtt_handlers
from collections import deque
import settings
from v1_logging import get_logger


logger = get_logger(__name__)
queue = deque(maxlen=2)


"""
Interface module that is responsible for the head movement.
It subscribes to MQTT topic "head". It expects a json object with:
* {"type": "head_move", "value": "up", "msec": optional_ms_movement_time}
* {"type": "head_move", "value": "down", "msec": optional_ms_movement_time}
* {"type": "head_position", "value": numeric_angle, "msec": optional_ms_movement_time}

Angle has to be between 5.1 and 104.9 degrees.
The head has to be parked before cycling power.
"""


def map_range(x, in_min, in_max, out_min, out_max):
    return (x - in_min) * (out_max - out_min) // (in_max - in_min) + out_min


class Ps5_Remote:
    LIRC_REMOTE = "LEGO_Combo_Direct"
    UP = "FORWARD_FORWARD"
    DOWN = "BACKWARD_BACKWARD"
    RIGHT = "FORWARD_BACKWARD"
    LEFT = "BACKWARD_FORWARD"
    RELEASED = "BRAKE_BRAKE"
    
    def __init__(self):
        self.last_message_ts = arrow.utcnow()
        self.running = True
        self.ir_client = lirc.Client()
        self.dualsense = pydualsense()
        detected = False
        while not detected:
            try:
                self.dualsense.init()
                detected = True
            except:
                time.sleep(5)
        self.dualsense.cross_pressed += self.cross_down
        self.dualsense.triangle_pressed += self.triangle_down
        self.dualsense.square_pressed += self.rectangle_down
        self.dualsense.circle_pressed += self.circle_down
        self.dualsense.dpad_up += self.dpad_up
        self.dualsense.dpad_down += self.dpad_down
        self.dualsense.left_joystick_changed += self.joystick
        self.dualsense.r2_changed += self.r2_down
        self.dualsense.l2_changed += self.l2_down
        
    def stop(self):
        self.running = False
        self.dualsense.close()

    def run_loop(self):
        time.sleep(0.5)
        loop_sleep_s = 0.25
        while self.running:
            time.sleep(loop_sleep_s)
            if(arrow.utcnow() - self.last_message_ts).total_seconds() > 4:
                pass
            
            if len(queue) > 0:
                message = queue.pop()
                logger.info("New item in queue, checking type")
                logger.info(f"message[type]: {message['type']}")
                self.last_message_ts = arrow.utcnow()
                
                if message["type"] == "head_position":
                    logger.info("Confirm: head_position")
                    continue
    
    def cross_down(self, state):
        self.dualsense.light.setColorI(128, 128, 0)  # set touchpad color to red
        print(f'cross {state}')
    
    def circle_down(self, state):
        self.dualsense.light.setColorI(255, 0, 0)  # set touchpad color to red
        print(f'circle {state}')
    
    def rectangle_down(self, state):
        self.dualsense.light.setColorI(255, 0, 0)  # set touchpad color to red
        print(f'circle {state}')
    
    def triangle_down(self, state):
        self.dualsense.light.setColorI(0, 128, 128)  # set touchpad color to green
        print(f'circle {state}')
        
    def dpad_up(self, state):
        if state:
            # self.dualsense.light.setColorI(0, 0, 255)  # set touchpad color to blue
            self.ir_client.send_once(self.LIRC_REMOTE, self.UP)
            return
        self.ir_client.send_once(self.LIRC_REMOTE, self.RELEASED)
    
    def dpad_left(self, state):
        if state:
            # self.dualsense.light.setColorI(0, 0, 255)  # set touchpad color to blue
            self.ir_client.send_once(self.LIRC_REMOTE, self.LEFT)
            return
    
    def dpad_right(self, state):
        if state:
            # self.dualsense.light.setColorI(0, 0, 255)  # set touchpad color to blue
            self.ir_client.send_once(self.LIRC_REMOTE, self.RIGHT)
            return
    
    def dpad_down(self, state):
        if state:
            # self.dualsense.light.setColorI(0, 0, 255)  # set touchpad color to blue
            self.ir_client.send_once(self.LIRC_REMOTE, self.DOWN)
            return
        self.ir_client.send_once(self.LIRC_REMOTE, self.RELEASED)
    
    def r2_down(self, state):
        to_servo = map_range(state, 0, 255, 10, 90)
        print(f'r1 {state} -> {to_servo}')
        mqttc.publish("head", json.dumps({"type": "head_position", "value": to_servo, "msec": 300}))
        
    def l2_down(self, state):
        to_servo = map_range(state, 0, 255, 10, 90)
        print(f'l2 {state} -> {to_servo}')
    
    def joystick(self, stateX, stateY):
        print(f'lj {stateX} {stateY}')
                
                    
movement = Ps5_Remote()
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
    mqttc.subscribe("remote", 0)


def signal_handler(signum, frame):
    signal.signal(signum, signal.SIG_IGN)  # ignore additional signals
    movement.stop()
    logger.info("All cleared, exiting.")
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
