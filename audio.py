import time
import json
import wave
import struct
import arrow
import pvporcupine
import pveagle
import pygame
from pvrecorder import PvRecorder
import settings
import librosa
import soundfile
from slicer2 import Slicer
from slicer2 import get_rms
import numpy as np
from v1_logging import get_logger

logger = get_logger("audio")


class Audio:
    FRAMES_MS = 512
    FRAME_SAMPLE_RATE = 16000
    
    def __init__(self, queue=None, mqttc=None):
        self.energy_threshold = 285  # minimum audio energy to consider for recording
        self.dynamic_energy_adjustment_damping = 0.15
        self.dynamic_energy_ratio = 1.5
        self.pause_threshold = 0.8  # seconds of non-speaking audio before a phrase is considered complete
        self.phrase_threshold = 0.3
        self.non_speaking_duration = 0.5
        self.pause_buffer_count = 18
        self.queue = queue
        self.mqttc = mqttc
        self._channels = 1
        self.speaker_profiles = settings.EAGLE_PROFILES
        
        pygame.mixer.init(44100, -16, self._channels, 1024)  # , devicename="Master"

        devices = PvRecorder.get_available_devices()
        logger.warning("Available recording devices:")
        self.device_id = 0
        for device in devices:
            logger.warning(f"{self.device_id}: {device}")
            if device == "ATR4697-USB Mono":
                break
            self.device_id += 1

        self.recorder = PvRecorder(frame_length=self.FRAMES_MS, device_index=self.device_id)
        try:
            profiles = list()
            for file_name in self.speaker_profiles:
                with open(settings.CURRENT_DIR + '/eagle/' + file_name + ".enroll", 'rb') as f:
                    profile = pveagle.EagleProfile.from_bytes(f.read())
                    profiles.append(profile)
            
            self.eagle = pveagle.create_recognizer(
                access_key=settings.PICOVOICE_API_KEY,
                speaker_profiles=profiles
            )
        except pveagle.EagleError as e:
            self.eagle = None
            logger.error("Failed to initialise pveagle", _error=e)
        
        self.porcupine = pvporcupine.create(
            access_key=settings.PICOVOICE_API_KEY,
            keyword_paths=[settings.CURRENT_DIR + '/porcupine/' + settings.PORCUPINE_WAKE_ZIEMNIACZEK,
                           settings.CURRENT_DIR + '/porcupine/' + settings.PORCUPINE_WAKE_KOMPOT,
                           settings.CURRENT_DIR + '/porcupine/' + settings.PORCUPINE_WAKE_GORA
                           ],
            model_path=settings.CURRENT_DIR + '/porcupine/porcupine_params_pl.pv',
        )
    
    def wait_for_wake_word(self):
        self.recorder.start()
        logger.info("Listening for wake word...")
        while True:
            audio_frame = self.recorder.read()
            keyword_index = self.porcupine.process(audio_frame)
            if keyword_index == 0 or keyword_index == 1:
                # detected `kompot`
                self.recorder.stop()
                logger.info("Detected robot name, stopping recording")
                self.play_audio(settings.CURRENT_DIR + "/audio_static/slucham.wav")
                return

            elif keyword_index == 2:
                self.recorder.stop()
                logger.info("Detected 'do gory', stopping recording")
                return

    def calculate_mean(self, audio_frame):
        return np.mean(audio_frame)
    
    def record_audio_pv(self, file_path: str, record_limit_s: int = 45) -> str:
        self.recorder.start()
        logger.info("Ask your query now:")
        frames = []
        volume_buffer = []
        pause_count = 0
        identified_speaker = "unknown"
        speaker_buffer = []
        while int(len(frames)/self.recorder.sample_rate) < record_limit_s:
            if len(self.queue) > 0:
                message = self.queue.pop()
                if message["type"] == "screen":
                    if self.mqttc:
                        self.mqttc.publish("screen", json.dumps({"type": "hide"}))
                        self.mqttc.publish("head", json.dumps({"type": "head_move", "value": "up"}))
                    break
            
            audio_frame = self.recorder.read()
            
            if self.eagle:
                try:
                    scores = self.eagle.process(audio_frame)
                    max_recognition_score = max(scores)
                    if max_recognition_score > 0.8:
                        max_index = scores.index(max_recognition_score)
                        speaker_buffer.append(self.speaker_profiles[max_index])
                except Exception as e:
                    logger.error("Issue with eagle speaker detection", _error=e)
            
            frames += audio_frame
            
            frames_mean = get_rms(audio_frame)[0]
            volume_buffer.append(frames_mean)
            
            if len(volume_buffer) > 15:
                buffer_mean = self.calculate_mean(volume_buffer)
                # print("Buffer mean: ", buffer_mean)
                volume_buffer = []
                
                if buffer_mean < self.energy_threshold:
                    # print("- silence")
                    print('-', end='', flush=True)
                    pause_count += 1
                else:
                    print('+', end='', flush=True)
                    # print("+ voice; buffer mean: ", buffer_mean)
                    pause_count = 0
                
                if pause_count > 6:
                    print("\n")
                    logger.info("Exceeded audio pause count", buffer_mean=buffer_mean)
                    break

        self.recorder.stop()
        with wave.open(file_path, "wb") as wav:
            wav.setparams((self._channels, 2, self.recorder.sample_rate, self.recorder.frame_length, "NONE", "NONE"))
            wav.writeframes(struct.pack("h" * len(frames), *frames))
        
        recording_duration = int(len(frames)/self.recorder.sample_rate)
        try:
            identified_speaker = max(set(speaker_buffer), key=speaker_buffer.count)
        except:
            pass
        
        logger.info("Recording saved", duration=recording_duration, speaker=identified_speaker)
        
        if 1 < recording_duration < 3:
            if identified_speaker == "unknown":
                logger.warning("It was a short recording and speaker is unknown - aborting")
                return False
            
            logger.info("It was a short recording but with audio", speaker=identified_speaker)
            return identified_speaker
        
        audio, sr = librosa.load(file_path, sr=self.recorder.sample_rate, mono=True)
        slicer = Slicer(
            sr=sr,
            threshold=-28,
            min_length=800,
            min_interval=150,
            hop_size=50,
            max_sil_kept=1200
        )
        chunks = slicer.slice(audio)
        if len(chunks) == 0:
            logger.info("It was all silence - breaking the interaction loop")
            return False
        
        with soundfile.SoundFile(file_path, mode="wb", samplerate=sr, channels=self._channels, format='wav') as sliced_wav:
            for chunk in chunks:
                sliced_wav.write(chunk)
        
        logger.info("Processed with Slicer2 to remove silence", chunks=len(chunks), speaker=identified_speaker)
        return identified_speaker

    def play_audio(self, audio_file, blocking: bool = True):
        logger.info("audio: Playing audio file")
        pygame.mixer.music.load(audio_file)
        pygame.mixer.music.play()
        if not blocking:
            return
        
        while pygame.mixer.music.get_busy():
            time.sleep(1)
        logger.info("audio: Done playing")


if __name__ == "__main__":
    a = Audio()
    a.wait_for_wake_word()
    a.record_audio_pv("example_query.wav")
