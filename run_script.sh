#!/usr/bin/bash

#eval $(ssh-agent)
#ssh-add /home/pi/.ssh/robot_v1

export PYENV_ROOT="/home/pi/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init --path)"

cd /home/pi/kompot
pyenv local 3.11.9
#git pull
python $1
