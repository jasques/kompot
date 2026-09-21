# Copy this file to settings.py and fill it in. settings.py is gitignored.
import os

# --- credentials --------------------------------------------------------------
OPENAI_API_KEY = "sk-..."              # https://platform.openai.com/api-keys
PICOVOICE_API_KEY = "..."              # https://console.picovoice.ai/

# --- wake words (Picovoice Porcupine) -----------------------------------------
# Train your own keyword files in the Picovoice Console (choose the Polish
# language and the Raspberry Pi platform) and drop them into porcupine/, together
# with the Polish acoustic model porcupine_params_pl.pv from
# https://github.com/Picovoice/porcupine/tree/master/lib/common
PORCUPINE_WAKE_ZIEMNIACZEK = "ziemniaczek_pl_raspberry-pi_v3_0_0.ppn"
PORCUPINE_WAKE_KOMPOT = "kompot_pl_raspberry-pi_v3_0_0.ppn"
PORCUPINE_WAKE_GORA = "do-gory_pl_raspberry-pi_v3_0_0.ppn"

# --- speaker identification (Picovoice Eagle) ---------------------------------
# One enrolment profile per person, stored as eagle/<name>.enroll. The name is
# prefixed to every transcribed question so the robot knows who is talking.
# Enrol with: eagle_demo_mic enroll --access_key $PICOVOICE_API_KEY --output_profile_path eagle/<name>.enroll
EAGLE_PROFILES = ["parent", "child"]

# One or two sentences the language model gets about the household, so it can
# address people by name. Keep it to what you are happy to send to OpenAI.
FAMILY_DESCRIPTION = "The children are Adam (7) and Ewa (5). Parents are Anna and Piotr."

# --- hardware -----------------------------------------------------------------
MQTT_BROKER = "localhost"
LX_BUS_PORT = "/dev/ttyUSB0"           # LewanSoul LX-16A bus adapter
UI_FULLSCREEN = True                   # False while developing on a desktop
AUDIO_DEVICE_NO = 0

# --- paths --------------------------------------------------------------------
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
NFS_DIRECTORY = "/nfs"                 # photos, printouts and memory.json land here
RAM_DIRECTORY = "/special"             # tmpfs for transient audio and images
LLM_AUDIO_RESPONSE_PATH = RAM_DIRECTORY + "/openai_response.mp3"
VOICE_RECORDING_PATH = RAM_DIRECTORY + "/recorded_audio.wav"
CAM_PREVIEW_PATH = RAM_DIRECTORY + "/preview.jpg"
TMP_IMAGE_PATH = RAM_DIRECTORY + "/last.jpg"
