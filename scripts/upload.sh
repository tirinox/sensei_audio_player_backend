#!/usr/bin/env sh

# Load environment variables from .env file
if [ -f .env ]; then
    . .env
else
    echo ".env file not found!"
    exit 1
fi

# Check if sshpass is installed
if ! command -v sshpass &> /dev/null
then
    echo "sshpass could not be found, please install it. (brew install sshpass)"
    exit 1
fi

# --dry-run only lists what would be uploaded and deleted on the host
RSYNC_FLAGS="-av --delete"
if [ "$1" = "--dry-run" ]; then
    RSYNC_FLAGS="-avn --delete"
    echo "Dry run: nothing will be changed on the host."
fi

sshpass -p "$SSH_PASSWORD" rsync $RSYNC_FLAGS  $AUDIO_SOURCE_PATH/* $SSH_USER@$SSH_HOST:$SSH_DEST_AUDIO_DB

if [ $? -eq 0 ]; then
    if [ "$1" = "--dry-run" ]; then
        echo "Dry run finished."
    else
        echo "Directory copied successfully!"
    fi
else
    echo "Error occurred during copying!"
    exit 1
fi
