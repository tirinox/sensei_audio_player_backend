import json
import os
import shlex
import subprocess

from pydub import AudioSegment
from pydub.silence import detect_silence


def detect_pieces(audio, padding=200, min_silence_len=1000, silence_thresh=-40):
    # Detect silence longer than 1000 ms (1 second)
    print(f"Detecting silence {padding = } ms, {min_silence_len = } ms, {silence_thresh = } dB...")

    silences = detect_silence(audio, min_silence_len=min_silence_len, silence_thresh=silence_thresh)

    if not silences:
        silences = [[0, len(audio)]]

    min_len = padding * 2

    # Generate a list of non-silent segments
    non_silent_segments = []
    voice_start = 0
    silence_end = 0
    for silence_start, silence_end in silences:
        # Add padding to the non-silent segments
        silence_start = max(0, silence_start + padding)
        silence_end = min(len(audio), silence_end - padding)

        # in case of overlapping silences
        if silence_start > silence_end:
            middle = (silence_start + silence_end) // 2
            silence_start = silence_end = middle

        if voice_start:
            voice_end = silence_start
            if voice_end - voice_start > min_len:
                non_silent_segments.append((voice_start, voice_end))
            else:
                print(f"Skipping segment from {voice_start / 1000:.2f} to {voice_end / 1000:.2f} "
                      f"because it's too short")
        voice_start = silence_end

    # Add the final segment if there's remaining audio after the last silence
    # todo check it>
    if silence_end < len(audio):
        voice_start = silence_end
        voice_end = len(audio)
        if voice_end - voice_start > min_len:
            non_silent_segments.append((silence_end, len(audio)))

    # Display the non-silent segments and let the user select one to play
    print("Non-silent segments available:")
    for idx, (start, end) in enumerate(non_silent_segments):
        print(
            f"{idx}: From {start / 1000:.2f} seconds to {end / 1000:.2f} seconds, duration: {(end - start) / 1000:.2f} seconds")
    return non_silent_segments


def split_file(audio_file, metadata, min_silence_len=None):
    metadata.clear()

    if min_silence_len is None:
        min_silence_len = int(os.environ.get('MIN_SILENCE_LEN_MS', 800))
    padding = int(os.environ.get('PADDING_MS', 200))
    silence_thresh = int(os.environ.get('SILENCE_THRESHOLD_DB', -40))

    non_silent_segments = detect_pieces(
        audio_file,
        min_silence_len=min_silence_len,
        padding=padding,
        silence_thresh=silence_thresh
    )

    metadata.set_segments(non_silent_segments)
