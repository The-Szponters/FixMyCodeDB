#!/bin/bash

if [ -z "$1" ]; then
    echo "Error: No volume name provided."
    echo "Usage: ./remove_database_data.sh <volume_name>"
    exit 1
fi

VOLUME_NAME=$1

if ! docker volume inspect "$VOLUME_NAME" > /dev/null 2>&1; then
    echo "Volume '$VOLUME_NAME' does not exist."
    exit 1
fi

echo "Removing volume: $VOLUME_NAME..."
docker volume rm "$VOLUME_NAME"

if [ $? -eq 0 ]; then
    echo "Success! Volume '$VOLUME_NAME' has been removed."
else
    echo "Failed to remove the volume."
    echo "Hint: Ensure no container (even stopped ones) is using this volume."
    echo "Try removing the container first: docker rm -f <container_id>"
fi