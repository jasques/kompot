from audio import Audio
from llms_openai import OpenAiWrapper
import time
import json
import paho.mqtt.client as mqtt
from collections import deque
import mqtt_handlers
import settings
import signal
import sys
from v1_logging import get_logger


logger = get_logger("app")
queue = deque(maxlen=1)


def on_message(mosq, obj, msg):
    try:
        command = json.loads(msg.payload.decode("utf-8"))
        msg = command
    except Exception as e:
        logger.error(f"ERROR: msg type = {type(msg)}: {msg}")
        logger.error(e)
    
    if type(msg) == dict:
        logger.info("Appending event to queue", ev=msg)
        queue.appendleft(msg)


def on_connect(mosq, obj, rc, rc2=None):
    logger.info("Connected.")
    mqttc.subscribe("touch", 0)
    mqttc.subscribe("llm", 0)


mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
mqttc.on_message = on_message
mqttc.on_connect = on_connect
mqttc.on_publish = mqtt_handlers.on_publish
mqttc.on_subscribe = mqtt_handlers.on_subscribe
mqttc.connect(settings.MQTT_BROKER, 1883, 60)
mqttc.loop_start()

TESTING_AUDIO = False


def signal_handler(signum, frame):
    logger.info("Finishing...")
    mqttc.publish("screen", json.dumps({"type": "hide"}))
    ai.summarise_conversations()
    ai.dump_memory_to_json()
    mqttc.publish("head", json.dumps({"type": "head_position", "value": 45, "msec": 2500}))
    signal.signal(signum, signal.SIG_IGN)  # ignore additional signals
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    a = Audio(queue=queue, mqttc=mqttc)
    ai = OpenAiWrapper(mqttc, audio=a, queue=queue)
    while True:
        mqttc.publish("head", json.dumps({"type": "head_position", "value": 55, "msec": 2000}))
        mqttc.publish("screen", json.dumps({"type": "mood", "value": "sleep"}))
        a.wait_for_wake_word()
        mqttc.publish("head", json.dumps({"type": "head_position", "value": 75, "msec": 1500}))
        mqttc.publish("head", json.dumps({"type": "wiggle_antenna", "seconds": 0.8}))
        while True:
            mqttc.publish("screen", json.dumps({"type": "mood", "value": "default"}))
            mqttc.publish("head", json.dumps({"type": "head_position", "value": 75, "msec": 1500}))
            mqttc.publish("screen", json.dumps({"type": "listen"}))
            
            queue.clear()
            speaker = a.record_audio_pv(settings.VOICE_RECORDING_PATH)
            if not speaker:
                logger.info("Interaction ended, breaking the loop")
                mqttc.publish("screen", json.dumps({"type": "mood", "value": "sleep"}))
                break
            
            mqttc.publish("screen", json.dumps({"type": "hide"}))
            mqttc.publish("head", json.dumps({"type": "head_move", "value": "up", "msec": 1000}))
            if TESTING_AUDIO:
                # # ##########################  only for testing  #############################
                a.play_audio(settings.VOICE_RECORDING_PATH)
                break
                
            if not ai.get_voice_answer_from_voice(voice_file=settings.VOICE_RECORDING_PATH, speaker=speaker):
                mqttc.publish("head", json.dumps({"type": "head_position", "value": 35, "msec": 1500}))
                mqttc.publish("head", json.dumps({"type": "hide_antenna", "value": 2}))
                ai.summarise_conversations()
                break
            
            mqttc.publish("screen", json.dumps({"type": "hide"}))
            ai.dump_memory_to_json()
            mqttc.publish("screen", json.dumps({"type": "hide"}))
            logger.info("\n\nDEBUG: speak again\n\n")
