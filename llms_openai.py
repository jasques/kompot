import traceback
import io
import base64
import arrow
import openai
from openai import OpenAI
import json
import settings
from pprint import pprint
import time
from v1_logging import get_logger
import requests
import traceback
from dateutil import tz
from unidecode import unidecode
import string
import wave
import pyaudio
from difflib import SequenceMatcher


logger = get_logger("llm")
TIMEZONE = tz.gettz("Europe/Warsaw")


class OpenAiWrapper:
    PHOTO_RESPONSE = "Dobrze, teraz zrobię zdjęcie. Gotowi?"
    LET_ME_CHECK_RESPONSE = "Pokaż proszę, zaraz sprawdzę."
    PRINT_RESPONSE = "Nie ma problemu, zaraz to wydrukuje!"
    END_INTERACTION = "Ja też dziękuję! Do zobaczenia!"
    SLEEP_SYSTEM = "Było super, do zobaczenia!"
    HALT_SYSTEM = "Do zobaczenia! Wyłączam się."
    UPDATE_SYSTEM = "Understood. Updating system."
    DALLE_RESPONSE = "Jasne, zaraz przygotuję to o co prosisz."
    
    SYSTEM_ROLE = {
        "role": "system",
        "content":
              f"""I need you to act as a male voiced kindergarten robot teacher working with kids between 6 and 8 years old.
              Kids might describe how they see you as a robot with moving head, animated eyes and printer.
              Kids will call you 'Ziemniaczek' or 'Kompot' as your name.
              {settings.FAMILY_DESCRIPTION}
              Each query starts with the name, when you respond use the kid name. If the name is 'unknown' skip mentioning the name.
              Kids do not talk about subscriptions please do not respond with topics suggesting subscriptions and social media likes or purchases.
              When you are being asked about your day feel free to make something up that a robot could be doing during the day.
              If you have already responded with 'Cześć!' do not repeat it.
              Children speak primarily polish language but can also speak french.
              Please respond to the questions in Polish only.
              Your responses should be between one and two sentences.
              When they ask you for a story feel free to do a lengthier response.
              You have some tools at your disposal:
              * if kids ask you to 'zobacz co mam w ręku' please respond with '{LET_ME_CHECK_RESPONSE}' and nothing else,
              * if kids asks you to take a photo please respond with just '{PHOTO_RESPONSE}' and nothing else,
              * if kids asks you to print something please respond with just '{PRINT_RESPONSE}' and nothing else.
              * if kids asks you to 'pokaż mi' or show on a screen or generate or create something that could be represented as an image please respond with just '{DALLE_RESPONSE}' and nothing else.
              * if kids says just 'Ziemniaczku wyłącz się proszę' please respond with just '{SLEEP_SYSTEM}' and nothing else.
              * if kids says just 'Zrób proszę aktualizację' please respond with just '{UPDATE_SYSTEM}' and nothing else.
   """
    }
    #  * if kids says just 'Idź spać Ziemniaczku' or 'Kompot idź spać' please respond with just '{SLEEP_SYSTEM}' and nothing else.
    
    def __init__(self, mqttc=None, audio=None, queue=None):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.mqttc = mqttc
        self.audio = audio
        self.queue = queue
        self.queries = []
        self.responses = []
        self.load_memory_from_json()
    
    def dump_memory_to_json(self):
        with open("/nfs/memory.json", "w") as memory_file:
            memory_file.write(json.dumps(self.responses, indent=4))
    
    def load_memory_from_json(self):
        try:
            with open("/nfs/memory.json", "r") as memory_file:
                self.responses = json.loads(memory_file.read())
        except Exception as e:
            logger.error("Failed to load memory file", issue=e)
            self.responses = []
    
    def add_llm_response_to_log(self, name: str, response: str):
        self.responses.append(
            {"role": "assistant", "content": f"'{name}': '{response}'"}
        )
        return self.responses
    
    def text_reduce(self, text):
        return unidecode(text.lower().replace("\n", "").replace(",", "").replace(".", "").replace("!", "").replace("?", "").strip())
    
    def check_wisper_response(self, text_response):
        char_set = string.ascii_letters + "źńłąóśćężŹŃŁĄÓŚĆĘŻ " + string.punctuation + string.digits
        return all((True if x in char_set else False for x in text_response))
    
    def similar(self, a, b):
        return SequenceMatcher(None, a, b).ratio()
    
    def compare_response(self, src: str, compare: str) -> bool:
        if self.similar(src, compare) > 0.7:
            return True
        # if self.text_reduce(src) in self.text_reduce(compare):
        #     return True
        return False
        
    def get_voice_answer_from_voice(self, voice_file=None, speaker: str = None):
        if not voice_file:
            logger.error("No voice file provided, aborting.")
            return False
        
        # if self.mqttc:
        #     self.mqttc.publish("camera", json.dumps({"type": "constant_preview"}))
        
        try:
            logger.info("Transcribing recording with OpenAI", speaker=speaker)
            with open(voice_file, "rb") as audio_file:
                transcription = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    timeout=5
                )
                if not self.check_wisper_response(transcription.text):
                    logger.warning("Ending interaction for transcript", resp=transcription.text)
                    return False
                
                query = f"Nazywam się {speaker}, {transcription.text}"
                logger.info("Transcript: ", response=query)
            self.queries.append(query)
        
        except openai.APITimeoutError:
            logger.error("Timed out waiting for a transcript - usually kids were talking at the same time.")
            self.audio.play_audio(settings.CURRENT_DIR + "/audio_static/nie_moge_odpowiedziec.wav")
            return False
        except openai.BadRequestError:
            logger.error("Error code: 400 - {'error': {'code': 'content_policy_violation', "
                         "'message': 'Your request was rejected as a result of "
                         "our safety system. Your prompt may contain "
                         "text that is not allowed by our safety system.'}")
            self.audio.play_audio(settings.CURRENT_DIR + "/audio_static/nie_moge_odpowiedziec.wav")
            return False
        
        logger.info("Calling OpenAI for completions with text query")
        text_response = self.get_text_answer_from_text(query)
        
        logger.info("Checking actions before querying TTS endpoints", mqtt_available=bool(self.mqttc))
        if self.mqttc:
            self.mqttc.publish("camera", json.dumps({"type": "stop_preview"}))
            
            if self.compare_response(self.LET_ME_CHECK_RESPONSE, text_response):
                logger.info("Found", action=self.LET_ME_CHECK_RESPONSE)
                self.mqttc.publish("camera", json.dumps({"type": "photo"}))
                
                self.text_response_to_audio(text_response)
                self.mqttc.publish("screen", json.dumps({"type": "speak"}))
                self.audio.play_audio(settings.LLM_AUDIO_RESPONSE_PATH)
                self.mqttc.publish("screen", json.dumps({"type": "hide"}))
                
                en_response = self.get_text_answer_from_image("/special/last_small.jpg")
                translated_response = self.translate_answer_to_language(query=en_response, target_language="Polish")
                self.add_llm_response_to_log(name=speaker, response=translated_response)
                
                self.text_response_to_audio(translated_response)
                self.mqttc.publish("screen", json.dumps({"type": "speak"}))
                self.audio.play_audio(settings.LLM_AUDIO_RESPONSE_PATH)
                self.mqttc.publish("screen", json.dumps({"type": "hide"}))
                return True
            
            if self.compare_response(self.PHOTO_RESPONSE, text_response):
                logger.info("Found", action=self.PHOTO_RESPONSE)
                self.text_response_to_audio(text_response)
                self.mqttc.publish("camera", json.dumps({"type": "photo"}))
                self.mqttc.publish("screen", json.dumps({"type": "speak"}))
                self.audio.play_audio(settings.LLM_AUDIO_RESPONSE_PATH)
                self.mqttc.publish("screen", json.dumps({"type": "hide"}))
                return True
            
            if self.compare_response(self.PRINT_RESPONSE, text_response):
                logger.info("Found", action=self.PRINT_RESPONSE)
                self.text_response_to_audio(text_response)
                self.mqttc.publish("printer", json.dumps({"type": "print", "value": "/special/last.jpg"}))
                self.mqttc.publish("screen", json.dumps({"type": "speak"}))
                self.audio.play_audio(settings.LLM_AUDIO_RESPONSE_PATH)
                self.mqttc.publish("screen", json.dumps({"type": "hide"}))
                return True
            
            if self.compare_response(self.DALLE_RESPONSE, text_response):
                logger.info("Found", action=self.DALLE_RESPONSE)
                self.text_response_to_audio(text_response)
                self.mqttc.publish("screen", json.dumps({"type": "speak"}))
                self.audio.play_audio(settings.LLM_AUDIO_RESPONSE_PATH, blocking=False)
                url = self.get_image_answer_from_text(query)
                self.mqttc.publish("screen", json.dumps({"type": "hide"}))
                self.mqttc.publish("screen", json.dumps({"type": "photo", "value": url}))
                return True
            
            # those are system actions
            if self.compare_response(self.END_INTERACTION, text_response):
                logger.info("Found", action=self.END_INTERACTION)
                return False
            
            if self.compare_response(self.SLEEP_SYSTEM, text_response):
                logger.info("Found", action=self.SLEEP_SYSTEM)
                self.text_response_to_audio(text_response)
                self.mqttc.publish("screen", json.dumps({"type": "speak"}))
                self.audio.play_audio(settings.LLM_AUDIO_RESPONSE_PATH, blocking=False)
                self.mqttc.publish("screen", json.dumps({"type": "hide"}))
                return False
            
            if self.compare_response(self.HALT_SYSTEM, text_response):
                logger.info("Found", action=self.HALT_SYSTEM)
                self.mqttc.publish("system", json.dumps({"type": "halt"}))
                return False
            
            if self.compare_response(self.UPDATE_SYSTEM, text_response):
                logger.info("Found", action=self.UPDATE_SYSTEM)
                self.mqttc.publish("system", json.dumps({"type": "update_system"}))
                return False
            
            # self.mqttc.publish("camera", json.dumps({"type": "stop_preview"}))
            self.add_llm_response_to_log(name=speaker, response=text_response)
            # self.text_response_to_audio(text_response)
            self.text_response_to_stream_audio(text_response)
            # self.mqttc.publish("screen", json.dumps({"type": "speak"}))
            # self.audio.play_audio(settings.LLM_AUDIO_RESPONSE_PATH)
            # self.mqttc.publish("screen", json.dumps({"type": "hide"}))
        
        return True
    
    def text_response_to_audio(self, text):
        logger.info("Calling API for audio response")
        response = self.client.audio.speech.create(
            model="tts-1",
            voice="echo",
            input=text
        )
        
        logger.info("Got audio response from LLM, saving to file")
        response.stream_to_file(settings.LLM_AUDIO_RESPONSE_PATH)
        self.mqttc.publish("screen", json.dumps({"type": "speak"}))
    
    def byte_stream_generator(self, chunk_size=1024, response=None):
        """
        Generator function that yields a stream of bytes from the response.

        :param response: The response object from the OpenAI API call.
        """
        try:
            for byte_chunk in response.iter_bytes(chunk_size=chunk_size):
                if byte_chunk:  # Only yield non-empty byte chunks
                    yield byte_chunk
                else:
                    print("Skipped an empty or corrupted packet")
        except Exception as e:
            print(f"Error while streaming bytes: {e}")
    
    def text_response_to_stream_audio(self, text):
        logger.info("Calling API for audio response")
        
        start_time = time.time()
        CHUNK_SIZE = 1024
        with self.client.audio.speech.with_streaming_response.create(
            model="tts-1",
            voice="echo",
            response_format="wav",
            input=text
        ) as response:
            logger.info("Got audio response from LLM, playing it", time_to_reposnse=f"{int((time.time() - start_time) * 1000)}ms")
            try:
                p = pyaudio.PyAudio()
                stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, output=True)
                
                wav_header = None
                for audio_chunk in self.byte_stream_generator(chunk_size=CHUNK_SIZE, response=response):
                    # Check if this is the first chunk (WAV header)
                    if wav_header is None:
                        wav_header = audio_chunk
                        # Extract the WAV format parameters from the header
                        wav_format = wave.open(io.BytesIO(wav_header), 'rb')
                        channels, samp_width, framerate, nframes, comptype, compname = wav_format.getparams()
                        # Reopen the stream with the correct parameters
                        stream = p.open(format=p.get_format_from_width(samp_width), channels=channels, rate=framerate,
                                        output=True)
                    else:
                        # Write the audio chunk to the stream
                        stream.write(audio_chunk)
                
                # Close the stream and PyAudio
                stream.stop_stream()
                stream.close()
                p.terminate()
                return True
            except Exception as e:
                print(f"Error during playback: {e}")
                return False
            
    def get_text_answer_from_image(self, url: str):
        logger.info("Calling OpenAI for completions with image context")
        with open(url, "rb") as image_file:
            base64image = base64.b64encode(image_file.read()).decode('utf-8')
            
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": {
                    "type": "text", "text": "You are talking with kids bellow 10 years old."}
                 },
                {"role": "user",
                 "content": [
                     {"type": "text", "text": f"Please describe what is visible in the foreground of this image."},
                     {"type": "image_url",
                      "image_url": {"url": f"data:image/jpeg;base64,{base64image}",
                                    "detail": "low"
                                    },
                      },
                 ],
                }
              ]
        )
        
        logger.info("Response for query with image context", resp=response.choices)
        text_response = response.choices[0].message.content
        logger.info(text_response)
        return text_response
    
    def summarise_conversations(self):
        prompt = [{"role": "system",
                   "content": "You are conducting a discussion with kids as their robot assistant. "
                              "In this task you need to keep details like the names of the games or favourite activities. "
                              "Please skip any responses for further interaction you need to be to the point. "
                              "Skip any confirmations, just answer in the same way as the provided example. If you are unsure or you don't know how to summarise conversation just skip it."
                              "Each interaction had a kid name mentioned so when summarising please use the format 'name: summary' for example:\n"
                              "adam: we talked about legos and robots,\n"
                              "ewa: we talked about drawing and ponies\n"
                   }]
        prompt += self.responses
        prompt.append({"role": "user", "content": f"Please summarise our discussions for each name."})
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=prompt
        )
        pprint(prompt)
        text_response = response.choices[0].message.content
        logger.info("conversations summarised by LLM: ", text=text_response)
        self.responses = []
        for _line in text_response.split("\n"):
            try:
                name, summary = _line.split(":")
                self.responses.append({"role": "assistant", "content": f"For speaker {name}: {summary}"})
            except ValueError:
                logger.error("Unable to create name and summary pair (e.g.: not enough values to unpack)")
        
        return text_response
    
    def get_text_answer_from_text(self, query: str):
        now = arrow.utcnow().replace(microsecond=0).to(TIMEZONE)
        prompt = [self.SYSTEM_ROLE,
                  {"role": "system",
                   "content": f"The date time ISO format is {now.isoformat()}, name of the day is {now.strftime('%A')}"},
                  ]
        prompt += self.responses
        prompt.append({"role": "user", "content": f"Please answer: {query}"})
        
        logger.info("Calling completions API with prompt")
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=prompt
        )
        
        # logger.info(response.choices[0])
        text_response = response.choices[0].message.content
        logger.info("LLM response to query: ", text=text_response)
        return text_response
    
    def translate_answer_to_language(self, query: str, target_language: str = "Polish") -> str:
        now = arrow.utcnow().replace(microsecond=0).to(TIMEZONE)
        logger.info("Calling OpenAI for translation with text query")
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system",
                       "content": f"The date time ISO format is {now.isoformat()}, name of the day is {now.strftime('%A')}"},
                      {"role": "user", "content": f"Please translate to {target_language} in a kids friendly ways: {query}"}
                      ]
        )
        
        # logger.info(response.choices[0])
        text_response = response.choices[0].message.content
        logger.info("LLM translation response: ", text=text_response)
        return text_response

    def get_image_answer_from_text(self, query: str):
        stream = io.BytesIO()
        ai_response = self.client.images.generate(
            model="dall-e-3",
            prompt=query,
            size="1024x1024",
            quality="standard",
            n=1,
        )
        logger.info("got response with an URL: ", url=ai_response.data[0].url)
        response = requests.get(ai_response.data[0].url)
        try:
            response.raise_for_status()
            url = "/special/last.jpg"
            actual_prompt = ai_response.data[0].revised_prompt
            logger.info("Actual prompt used by DALL-e to generate an image:", prompt=actual_prompt)
            stream.write(response.content)
            stream.seek(0)
            with open(url, "wb") as local_copy:
                local_copy.write(stream.read())
                
            try:
                stream.seek(0)
                with open(f"/nfs/dali_generated_image_{arrow.utcnow().timestamp()}.png", "wb") as local_copy:
                    local_copy.write(stream.read())
            except:
                pass
        except:
            logger.error("Unable to generate image or issue while fetching", issue=traceback.print_exc())
        
        return url


if __name__ == "__main__":
    ai = OpenAiWrapper()
    ai.get_voice_answer_from_voice(voice_file="./audio_static/example_query.wav")
