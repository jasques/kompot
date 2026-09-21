# from gpiozero import LED
import random
import pygame
from pygame.locals import *
# import pygame.gfxdraw as fx
import pygame.freetype
from io import BytesIO
import requests
import PIL
from PIL import Image, ImageOps
from collections import deque
import sys
import os
import json
import time
import arrow
import settings
from pygame.sprite import Sprite
import paho.mqtt.client as mqtt
from collections import deque
import mqtt_handlers
from v1_logging import get_logger

logger = get_logger(__name__)


"""
Interface module that is responsible for the expressions show on the display.
It subscribes to MQTT topic "screen". It expects a json object with:
* {"type": "photo", "value": photo_url}
* {"type": "listen"}
* {"type": "speak"}
"""


queue = deque(maxlen=2)
# current_dir = os.path.dirname(os.path.abspath(__file__))
current_dir = os.path.dirname(os.path.abspath("v1"))
ROBOT_EYES = current_dir + "/sprites/leonardo1.png"

MARGIN = 60
Y_MARGIN = 50
COVER_WIDTH = 300
COVER_HEIGHT = 300
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 400
RUN_FULLSCREEN = settings.UI_FULLSCREEN

EYE_SIZE = 300
GLOBAL_FRAME_INDEX = 0
GLOBAL_FPS = 24

pygame.init()
pygame.mixer.quit()
GAME_FONT = pygame.freetype.Font(current_dir + "/fonts/Roboto-Thin.ttf", 24)

if RUN_FULLSCREEN:
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.FULLSCREEN)
    pygame.mouse.set_visible(False)
    pygame.mouse.set_cursor((8, 8), (0, 0), (0, 0, 0, 0, 0, 0, 0, 0),
                            (0, 0, 0, 0, 0, 0, 0, 0))
else:
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))


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


mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
mqttc.on_message = on_message
mqttc.on_connect = on_connect
mqttc.on_publish = mqtt_handlers.on_publish
mqttc.on_subscribe = mqtt_handlers.on_subscribe
mqttc.connect(settings.MQTT_BROKER, 1883, 60)
# run loop in a separate thread
mqttc.loop_start()


class TimedAnimation(Sprite):
    
    def __init__(self, frames, pos, fps=GLOBAL_FPS):
        Sprite.__init__(self)
        self.frames = frames  # store frames in a list
        self.image = frames[0]
        self.rect = self.image.get_rect(topleft=pos)
        self.current = 0  # current image of the animation
        self.playing = 0  # to know if it is playing
        self._next_update = 0  # next time it has to be updated in ms
        self._inv_period = fps / 1000.  # 1./period of the animation in ms
        self._start_time = 0  # has to be set when the animation is started
        self._paused_time = 0
        self._pause_start = 0
        self._frames_len = len(self.frames)
        self.surface = pygame.Surface((self.image.get_width(), self.image.get_height()), flags=0, depth=16)
        self.current_frame = 0
    
    def update(self, dt, t):
        # dt: time that has passed in last pass through main loop,  t: current time
        if self.playing:
            # period is duration of one frame, so dividing the time the animation
            # is running by the period of one frame on gets the number of frames
            self.current = int((t - self._start_time - self._paused_time) * self._inv_period)
            self.current %= self._frames_len
            # update image
            self.image = self.frames[self.current]
            # only needed if size changes between frames
            self.rect = self.image.get_rect(center=self.rect.center)
    
    def get_frame_surface(self):
        self.current_frame += 1
        if self.current_frame > self._frames_len-1:
            self.current_frame = 0
        self.image = self.frames[self.current_frame]
        # only needed if size changes between frames
        self.rect = self.image.get_rect(center=self.rect.center)
        # self.surface.fill((0, 0, 0, 255))
        self.surface.blit(self.image, (0, 0))
        return self.surface


class StatusAnim(Sprite):
    STATUS_WIDTH = 400
    
    def __init__(self, frames: list, pos, fps=GLOBAL_FPS):
        Sprite.__init__(self)
        self.pos = pos
        self.frames = {"listen": frames}  # store frames in a list
        self.image = self.frames["listen"][0]  # provide at least {"default": [Image()]}
        self.playing = 0  # to know if it is playing
        self.stopped = False
        self.surface = pygame.Surface((self.STATUS_WIDTH, SCREEN_HEIGHT), flags=0, depth=16)
        self.current_frame = 0
        self.mode = "listen"
        self.last_animation = arrow.utcnow()
    
    def anim_ts_delta(self):
        return (arrow.utcnow() - self.last_animation).total_seconds()
    
    def play(self):
        self.playing = True
        self.stopped = False
    
    def stop(self):
        self.stopped = True
        self.last_animation = arrow.utcnow()
        self.current_frame = 0
    
    def stop_and_hide(self):
        self.stopped = True
        self.last_animation = arrow.utcnow()
        self.current_frame = 0
    
    def add_mode(self, frames: list, mode: str):
        self.frames[mode] = frames
    
    def set_mode(self, mode: str):
        self.mode = mode
        self.playing = True
    
    def get_next_frame(self) -> pygame.Surface:
        if self.stopped:
            self.surface.fill(pygame.color.THECOLORS["black"])
            return self.surface
        
        # if not self.playing:
        #     self.mode = "listen"
        #     self.image = self.frames[self.mode][0]
        #     return self.surface
        
        if len(self.frames[self.mode]) > 1:
            self.current_frame += 1
            if self.current_frame > len(self.frames[self.mode]) - 1:
                self.last_animation = arrow.utcnow()
                self.current_frame = 0
                # self.playing = False
        
        self.image = self.frames[self.mode][self.current_frame]
        self.surface.fill(pygame.color.THECOLORS["black"])
        self.surface.blit(self.image, (0, 0))
        return self.surface


class EyeAnimation(Sprite):
    
    def __init__(self, frames: list, pos, fps=GLOBAL_FPS):
        Sprite.__init__(self)
        self.frames = {"default": frames}  # store frames in a list
        self.image = self.frames["default"][0]  # provide at least {"default": [Image()]}
        self.playing = 0  # to know if it is playing
        self.stopped = False
        # self._frames_len = len(self.frames)
        # self.surface = pygame.Surface((self.image.get_width(), self.image.get_height()), flags=0, depth=16)
        self.surface = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), flags=0, depth=16)
        self.current_frame = 0
        self.mood = "default"
        self.last_animation = arrow.utcnow()
        self.pos = pos
    
    def anim_ts_delta(self):
        return (arrow.utcnow() - self.last_animation).total_seconds()
    
    def random_mood(self):
        choice = "sleep"
        while choice == "sleep":
            choice = random.choice(list(self.frames.keys()))
        return choice
    
    def play(self):
        self.playing = True
        self.stopped = False
    
    def stop(self):
        self.stopped = True
        self.last_animation = arrow.utcnow()
        self.current_frame = 0
    
    def add_mood(self, frames: list, mood: str):
        self.frames[mood] = frames

    def set_mood(self, mood: str):
        self.mood = mood
        self.playing = True

    def get_next_frame(self, one_eye_only: bool = False) -> pygame.Surface:
        if not self.playing:
            self.mood = "default"
            self.image = self.frames[self.mood][0]
            return self.surface
        
        self.current_frame += 1
        if self.current_frame > len(self.frames[self.mood]) - 1:
            self.last_animation = arrow.utcnow()
            self.current_frame = 0
            self.playing = False
        
        self.image = self.frames[self.mood][self.current_frame]
        if one_eye_only:
            self.surface.fill(pygame.color.THECOLORS["black"])
            self.surface.blit(self.image, (SCREEN_WIDTH/2-150, MARGIN))
            return self.surface
        
        self.surface.blit(self.image, (MARGIN, Y_MARGIN))
        self.surface.blit(
            pygame.transform.flip(self.image, False, False), (SCREEN_WIDTH-COVER_WIDTH-MARGIN, Y_MARGIN)
        )
        return self.surface


def load_image(path: str, screen: pygame.display = None):
    if not screen:
        return
    
    try:
        pilimage = ImageOps.contain(Image.open(path), (SCREEN_WIDTH, SCREEN_HEIGHT)).convert("RGBA")
    except PIL.UnidentifiedImageError:
        logger.error("Failed to load image", p=path)
        return False
    except OSError:
        logger.error("Failed to load image", p=path)
        return False

    cover = pygame.image.fromstring(pilimage.tobytes(), pilimage.size, pilimage.mode)
    screen.fill(pygame.color.THECOLORS["darkgray"])
    screen.blit(cover, (SCREEN_WIDTH/2 - cover.get_width()/2, 0))
    pygame.display.flip()


def load_sprites(sprite_name: str, number_of_frames: int, flip_vertical: bool = False, flip_horizontal: bool = False):
    frames = []
    for i in range(number_of_frames):
        frames.append(
            pygame.transform.flip(
                pygame.image.load(current_dir + f"/sprites/{sprite_name}{i}.png")
                , flip_vertical, flip_horizontal)
        )
    for i in range(number_of_frames):
        frames.append(frames[-1 + number_of_frames - i])
    return frames.copy()


sprites_evil = load_sprites("look evil/eye evil ", 6)
sprites_left = load_sprites("look left/eye left ", 11)
sprites_blink = load_sprites("eye blink/eyes blink2", 12)
sprites_sleep = load_sprites("eyes sleep/eyes_sleep", 2)

eye = EyeAnimation(sprites_blink, (0, 0))
eye.add_mood(frames=sprites_left, mood="look left")
eye.add_mood(frames=sprites_sleep, mood="sleep")
# eye.add_mood(frames=sprites_evil, mood="evil look")

sprites_listen = load_sprites("statuses/microphone", 1)
sprites_speak = load_sprites("statuses/speak", 1)
statuses = StatusAnim(sprites_listen, (SCREEN_WIDTH/2-200, 0))
statuses.add_mode(frames=sprites_speak, mode="speak")


def show_status(id: str) -> bool:
    if id in ["hide", "photo", "fast_photo"]:
        statuses.stop_and_hide()
        return False
    
    try:
        statuses.set_mode(id)
        statuses.play()
    except:
        logger.error("function show_status had issue - probably incorrect 'id' was passed or the guard is outdated")
        return False
    return True


clock = pygame.time.Clock()
running = True
eye.play()
pygame.display.flip()
mqttc.connect(settings.MQTT_BROKER, 1883, 30)
mqttc.publish("head", json.dumps({"type": "head_position", "value": 45, "msec": 2500}))
time.sleep(0.5)

while running:
    if eye.mood != "sleep":
        if not eye.stopped:
            if not eye.playing and eye.anim_ts_delta() > random.randrange(7, 30):
                eye.set_mood(eye.random_mood())
                eye.play()
    
    screen.blit(eye.get_next_frame(one_eye_only=False), dest=eye.pos)
    
    if statuses.playing:
        screen.blit(statuses.get_next_frame(), statuses.pos)
    
    if len(queue) > 0:
        message = queue.pop()
        if message["type"] == "photo":
            load_image(message["value"], screen)
            time.sleep(6)
        
        if message["type"] == "fast_photo":
            statuses.stop()
            load_image(message["value"], screen)
            time.sleep(0.3)
            continue
        
        if message["type"] == "mood":
            mood = message.get("value", "sleep")
            if mood == "sleep":
                eye.set_mood("sleep")
                screen.blit(statuses.get_next_frame(), statuses.pos)
                eye.stop()
                pygame.display.flip()
                continue
            eye.set_mood(mood)
            eye.play()
        else:
            # it is guarded internally so no need to check
            if show_status(message["type"]):
                eye.stop()
            else:
                eye.play()

    for event in pygame.event.get():
        # logger.debug("event type: ", _type=event.type)
        # logger.debug(event)
            
        if event.type == pygame.MOUSEBUTTONDOWN:
            '''
            {'window': None}
            {'pos': (741, 260), 'rel': (0, 0), 'buttons': (0, 0, 0), 'touch': True, 'window': None}
            {'pos': (741, 260), 'button': 1, 'touch': True, 'window': None}
            {'touch_id': 7, 'finger_id': 31, 'x': 0.5794039964675903, 'y': 0.6516069173812866, 'dx': 0.0, 'dy': 0.0, 'pressure': 0.0, 'window': None}
            '''
            logger.info("Screen touched - MOUSEBUTTONDOWN")
            mqttc.publish("touch", json.dumps({"type": "screen", "value": "finger-down"}))
            mqttc.publish("head", json.dumps({"type": "head_move", "value": "up"}))
            continue
        
        if event.type == pygame.MOUSEBUTTONUP:
            '''
            {'pos': (741, 260), 'button': 1, 'touch': True, 'window': None}
            {'touch_id': 7, 'finger_id': 31, 'x': 0.5794039964675903, 'y': 0.6516069173812866, 'dx': 0.0, 'dy': 0.0, 'pressure': 0.0, 'window': None}
            '''
            logger.info("Screen released - MOUSEBUTTONUP")
            # mqttc.publish("touch", json.dumps({"type": "screen", "value": "finger-up"}))
            continue

        if event.type == QUIT:
            mqttc.disconnect()
            pygame.quit()
            sys.exit()
        
        if event.type == KEYDOWN:
            if event.key == K_ESCAPE:
                running = False
    
    pygame.display.flip()
    clock.tick(GLOBAL_FPS)

mqttc.disconnect()
pygame.quit()
sys.exit()
