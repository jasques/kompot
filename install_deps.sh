#!/bin/bash
# audio should be using pulseaudio
echo "Select speakers index:"
pacmd list-sinks

#use the input id when setting sink
# pacmd set-sink-port 0 analog-output-headphones

echo "Select microphone index:"
pacmd list-sources

#use the input id when setting source
# pacmd set-source-port 0 usb-microphone

# for permanent change edit /etc/pulse/default.pa
# set-default-sink 0
# set-sink-port 0 analog-output-headphones

#edit nano /etc/xdg/lxsession/LXDE-pi/autostart
#
# expected file content:
#@lxpanel --profile LXDE-pi
#@pcmanfm --desktop --profile LXDE-pi
#@xscreensaver -no-splash
#@xrandr --output HDMI-A-0 --rotate left
#@xrandr --output HDMI-A-1 --rotate left
#@xrandr --output HDMI-0 --rotate left
#@xrandr --output HDMI-1 --rotate left
#@lxterminal -e /home/pi/kompot/run_script.sh app.py
#@lxterminal -e /home/pi/kompot/run_script.sh interface.py



apt-get update
apt-get install mosquitto supervisor libhidapi-dev

# udev rules: DualSense gamepad (from pydualsense), thermal printer, gpio/i2c/serial groups
sudo cp install/70-dualsense.rules install/90-myusb.rules install/99-com.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules

curl https://pyenv.run | bash
echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc
echo 'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc
echo 'eval "$(pyenv init -)"' >> ~/.bashrc
echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.profile
echo 'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.profile
echo 'eval "$(pyenv init -)"' >> ~/.profile
echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bash_profile
echo '[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bash_profile
echo 'eval "$(pyenv init -)"' >> ~/.bash_profile

pyenv install 3.11.9
pyenv global 3.11.9

cp install/movement.service /etc/systemd/system/movement.service
systemctl enable movement

cd /usr/share/plymouth/themes/pix
sudo mv splash.png splash_default.png
sudo cp "$HOME/kompot/install/sleeping.png" splash.png
sudo plymouth-set-default-theme --rebuild-initrd pix

#for zsh use:
#echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.zshrc
#echo '[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.zshrc
#echo 'eval "$(pyenv init -)"' >> ~/.zshrc

#eagle speaker enrolment
# eagle_demo_mic enroll --access_key "{PICOVOICE_API_KEY}" --output_profile_path eagle/<name>.enroll