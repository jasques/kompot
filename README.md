# Kompot v1

Kompot (also answering to *Ziemniaczek*, "little potato") is a desk robot for two
children, built in 2024 around a Raspberry Pi 5. It sleeps with its eyes closed,
wakes on a Polish wake word, lifts its head, wiggles its antenna, works out who is
talking, listens, and answers in Polish in one or two sentences. It can look at
what you are holding, take a photo, print it on a thermal printer, draw a picture
on request, and remembers what each child talked about between sessions.

This is the first version, written as a handful of Python processes talking over
MQTT. It has since been replaced by a ROS 2 rewrite; the story of both is in
[Kompot: a robot that keeps eye contact, listens, and answers](https://wemakerobots.com/en/robots/kompot-a-robot-that-looks-listens-and-answers/).
The code is published as it last ran on the robot, with personal data and
licensed model files taken out (see [What is not included](#what-is-not-included)).

## Hardware

- Raspberry Pi 5 with active cooler, Raspberry Pi OS (Bookworm, 64-bit, desktop)
- 7.9" HDMI LCD, 1280x400, mounted rotated (see the `xrandr` notes in `install_deps.sh`)
- Raspberry Pi Camera Module 3 (`picamera2`)
- LewanSoul LX-16A serial bus servo for head tilt, on a USB bus adapter (`pylx16a`)
- SG90 micro servo for the antenna on a PCA9685 PWM board, channel 15 (`adafruit-circuitpython-servokit`)
- USB thermal receipt printer, ESC/POS, USB id `28e9:0289` (`python-escpos`)
- USB mono microphone (the code looks for an `ATR4697-USB Mono` device and falls back to device 0)
- Speaker on the Pi's audio output via PulseAudio
- VL53L0X time-of-flight distance sensor on I2C (`distance_sensor.py`, optional)
- Sony DualSense controller over USB or Bluetooth for driving by hand (`ps_remote.py`, optional)
- An XL4015 buck converter feeding the servos from the main supply

## How it is put together

Every piece is its own process and they talk through a local Mosquitto broker.
If the face crashes the ears keep working, and each piece can be restarted or
tested on its own with `dummy_publish.py`.

| Process | File | Listens on | Does |
|-|-|-|-|
| app | `app.py` | `touch`, `llm` | The main loop: sleep, wake word, record, transcribe, answer, speak |
| interface | `interface.py` | `screen` | pygame face: eye sprites, blink, look, sleep, listen/speak status, photo display |
| movement | `movement.py` | `head` | Head tilt between 5 and 105 degrees, antenna wiggle and hide |
| camera | `camera.py` | `camera` | Photos, preview frames, images for the vision model |
| printer | `printer.py` | `printer` | Text, photos and QR codes on the thermal printer |
| system | `system.py` | `system` | Halt, and self-update by `git pull` + supervisor restart |
| ps_remote | `ps_remote.py` | `remote` | DualSense gamepad and LEGO IR control (optional) |

Messages are small JSON objects such as
`{"type": "head_position", "value": 75, "msec": 1500}` or `{"type": "mood", "value": "sleep"}`.

The voice loop in `audio.py` and `llms_openai.py`:

1. Picovoice **Porcupine** waits for one of three Polish wake words, on device.
2. Picovoice **Eagle** compares the recording with the enrolled voice profiles and
   prefixes the question with the speaker's name, or `unknown`.
3. Recording stops on silence (RMS threshold plus `slicer2.py` to trim it).
4. OpenAI **Whisper** transcribes, **gpt-4o-mini** answers under a system prompt that
   fixes the persona (a robot kindergarten teacher, Polish only, short answers,
   no subscriptions or shopping talk), and **tts-1** speaks the answer, streamed
   straight to the speaker.
5. A few phrases are matched with `difflib.SequenceMatcher` and turned into actions
   instead of answers: take a photo, print, look at what I am holding, draw
   something (DALL·E 3), go to sleep, shut down, update yourself.
6. At the end of a session the conversation is summarised per child into
   `/nfs/memory.json` and fed back into the next session.

Wake word detection and speaker identification are the only parts that run on the
robot. Everything else is a call to OpenAI. That was the assumption of the whole
design: keep the robot cheap and let the cloud do the thinking.

## Build and run

You need an OpenAI API key and a Picovoice account. Both have free tiers that are
enough for a robot used by two children.

### 1. Operating system and system packages

On a fresh Raspberry Pi OS install, clone this repository to `/home/pi/kompot`
(the supervisor and systemd files in `install/` assume that path and the `pi`
user; edit them if yours differ), then read `install_deps.sh` before running it.
It installs Mosquitto, supervisor and `libhidapi`, copies the udev rules for the
gamepad, printer and GPIO groups, installs `pyenv` with Python 3.11.9, enables the
`movement` systemd service and swaps the boot splash for the sleeping face.

```sh
sudo apt install -y mosquitto supervisor libhidapi-dev portaudio19-dev libsndfile1 \
    libsdl2-2.0-0 libsdl2-mixer-2.0-0 libsdl2-image-2.0-0 libsdl2-ttf-2.0-0 \
    python3-picamera2 liblirc-dev
cd /home/pi/kompot
bash install_deps.sh
```

Create the two directories the code writes to. `/special` is a tmpfs for transient
audio and images, `/nfs` is where photos, printouts and `memory.json` are kept
(any directory works, it does not have to be NFS):

```sh
sudo mkdir -p /nfs /special
sudo chown pi:pi /nfs /special
echo "tmpfs /special tmpfs defaults,size=64m,uid=pi,gid=pi 0 0" | sudo tee -a /etc/fstab
```

### 2. Python environment

```sh
cd /home/pi/kompot
pyenv install 3.11.9        # skipped if install_deps.sh already did it
pyenv local 3.11.9
pip install -r requirements.txt
```

`picamera2` comes from the OS package and is picked up from the system site-packages.

### 3. Picovoice files

- In the [Picovoice Console](https://console.picovoice.ai/) train three Porcupine
  keywords (language Polish, platform Raspberry Pi), download the `.ppn` files into
  `porcupine/` and put the Polish model `porcupine_params_pl.pv` from the
  [Porcupine repository](https://github.com/Picovoice/porcupine/tree/master/lib/common)
  beside them.
- Enrol each person who will talk to the robot with the Eagle demo, one profile per
  person, into `eagle/<name>.enroll`:

  ```sh
  eagle_demo_mic enroll --access_key "$PICOVOICE_API_KEY" --output_profile_path eagle/anna.enroll
  ```

### 4. Settings

```sh
cp settings.example.py settings.py
```

Fill in the keys, the keyword file names, the list of enrolled names, the serial
port of the LX-16A adapter and a line about your household for the language model.
`settings.py` is gitignored.

### 5. Try it by hand

Start the broker, then each process in its own terminal:

```sh
sudo systemctl enable --now mosquitto
./run_script.sh movement.py
./run_script.sh interface.py      # UI_FULLSCREEN = False while developing
./run_script.sh camera.py
./run_script.sh printer.py
./run_script.sh app.py
```

`dummy_publish.py` sends single messages to a topic, which is the quickest way to
check the head, the face or the printer without the voice loop.

### 6. Run at boot

`movement.py` runs as a systemd service (`install/movement.service`), the rest
under supervisor:

```sh
sudo cp install/movement.service /etc/systemd/system/
sudo systemctl enable --now movement
sudo cp install/app.conf install/camera.conf install/printer.conf install/system.conf /etc/supervisor/conf.d/
sudo supervisorctl reread && sudo supervisorctl update
```

The face (`interface.py`) needs the X display, so it is started from the LXDE
autostart file rather than supervisor; the exact lines, including the `xrandr`
rotation, are in the comments at the top of `install_deps.sh`. `move_down.py`
parks the head before shutdown.

## What is not included

- **Wake-word models and voice profiles.** The `.ppn`, `.pv` and `.enroll` files are
  tied to a Picovoice account and, in the case of Eagle, are voiceprints of real
  people. Train and enrol your own (step 3).
- **The household.** Names of the children and parents were in the system prompt;
  they now come from `FAMILY_DESCRIPTION` and `EAGLE_PROFILES` in `settings.py`.
- **CAD.** The Fusion 360 model and the 3D-printed parts are not in this repository.
- **Unused art.** Only the sprites the face actually loads are here; design sources
  and stock images were left out.

## Licence

MIT, see `LICENSE`. `fonts/Roboto-Thin.ttf` is Apache-2.0 (`fonts/LICENSE-Roboto.txt`).
The LX-16A driver is [pylx16a](https://github.com/ethanlipson/PyLX-16A) from PyPI;
`slicer2.py` is the silence slicer from
[audio-slicer](https://github.com/openvpi/audio-slicer) (MIT).
