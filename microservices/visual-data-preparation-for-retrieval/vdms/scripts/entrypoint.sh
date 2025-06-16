#!/bin/bash
# Activates the virtual environment and runs any command given to the docker container

set -e
. $VENV_PATH/bin/activate

exec "$@"