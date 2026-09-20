#!/usr/bin/env sh
# Stands in for scripts/upload.sh (EDITOR_UPLOAD_CMD): prints what rsync -av --delete would print, touches nothing.
# AUDIO_SOURCE_PATH comes from the environment of the editor.

if [ "$1" = "--dry-run" ]; then
    echo "Dry run: nothing will be changed on the host."
fi

echo "building file list ... done"
echo "deleting JPTEST/lb_removed_on_disk.mp3_segments.json"
echo "deleting JPTEST/lb_removed_on_disk.mp3"
cd "$AUDIO_SOURCE_PATH" || exit 1
for dir in */; do
    echo "$dir"
    ls "$dir" | grep -E 'index\.json|_segments\.json' | head -4 | while read -r name; do
        sleep 0.2
        echo "$dir$name"
    done
done
echo ""
echo "sent 12345 bytes  received 678 bytes  8682.00 bytes/sec"
echo "total size is 9876543  speedup is 758.33"

if [ -n "$FAKE_UPLOAD_FAIL" ]; then
    echo "rsync error: connection unexpectedly closed"
    exit 12
fi

if [ "$1" = "--dry-run" ]; then
    echo "Dry run finished."
else
    echo "Directory copied successfully!"
fi
