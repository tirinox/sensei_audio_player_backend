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

    min_len = padding * 2

    # Generate a list of non-silent segments
    non_silent_segments = []
    voice_start = 0
    for silence_start, silence_end in silences:
        leading_silence = silence_start == 0

        # Add padding to the non-silent segments
        silence_start = max(0, silence_start + padding)
        silence_end = min(len(audio), silence_end - padding)

        # in case of overlapping silences
        if silence_start > silence_end:
            middle = (silence_start + silence_end) // 2
            silence_start = silence_end = middle

        if not leading_silence:
            voice_end = silence_start
            if voice_end - voice_start > min_len:
                non_silent_segments.append((voice_start, voice_end))
            else:
                print(f"Skipping segment from {voice_start / 1000:.2f} to {voice_end / 1000:.2f} "
                      f"because it's too short")
        voice_start = silence_end

    # Add the final segment if there's remaining audio after the last silence
    if len(audio) - voice_start > min_len:
        non_silent_segments.append((voice_start, len(audio)))

    # Display the non-silent segments and let the user select one to play
    print("Non-silent segments available:")
    for idx, (start, end) in enumerate(non_silent_segments):
        print(
            f"{idx}: From {start / 1000:.2f} seconds to {end / 1000:.2f} seconds, duration: {(end - start) / 1000:.2f} seconds")
    return non_silent_segments


def detect_pieces_in_range(audio, start, end, **kwargs):
    """Same as detect_pieces, but only for audio[start:end]; returned positions are absolute"""
    pieces = detect_pieces(audio[start:end], **kwargs)
    return [(piece_start + start, piece_end + start) for piece_start, piece_end in pieces]


def find_pauses(audio, start, end, min_pause=120, silence_thresh=-40):
    """Silent intervals strictly inside audio[start:end] (not touching its edges), absolute ms, longest first"""
    piece = audio[start:end]
    silences = detect_silence(piece, min_silence_len=min_pause, silence_thresh=silence_thresh, seek_step=5)
    pauses = [(s + start, e + start) for s, e in silences if s > 0 and e < len(piece)]
    pauses.sort(key=lambda pause: pause[0] - pause[1])
    return pauses


def find_pauses_relaxed(audio, start, end, min_pause=120, silence_thresh=-40):
    """Same, but if nothing is that quiet (noisy recording), raise the threshold step by step"""
    for thresh in (silence_thresh, silence_thresh + 6, silence_thresh + 12):
        pauses = find_pauses(audio, start, end, min_pause=min_pause, silence_thresh=thresh)
        if pauses:
            return pauses
    return []


def cut_around_pause(pause, padding=200):
    """Where the first part ends and the second one starts, if a segment is cut at this pause"""
    pause_start, pause_end = pause
    first_end = pause_start + padding
    second_start = pause_end - padding
    if first_end > second_start:
        first_end = second_start = (pause_start + pause_end) // 2
    return first_end, second_start


def pick_cut(audio, start, end, at_ms=None, padding=200, silence_thresh=-40, snap_ms=150):
    """
    Choose where to cut the segment [start, end].
    No at_ms: at the longest pause inside. With at_ms: at the pause under it (or within snap_ms),
    otherwise exactly there. Returns (first_end, second_start) or None if there is no pause to cut at.
    """
    pauses = find_pauses_relaxed(audio, start, end, silence_thresh=silence_thresh)
    if at_ms is None:
        return cut_around_pause(pauses[0], padding) if pauses else None

    for pause_start, pause_end in pauses:
        if pause_start - snap_ms <= at_ms <= pause_end + snap_ms:
            return cut_around_pause((pause_start, pause_end), padding)
    return at_ms, at_ms


def split_params(min_silence_len=None, padding=None, silence_thresh=None):
    """Fill the missing splitter parameters from the environment"""
    if min_silence_len is None:
        min_silence_len = int(os.environ.get('MIN_SILENCE_LEN_MS', 800))
    if padding is None:
        padding = int(os.environ.get('PADDING_MS', 200))
    if silence_thresh is None:
        silence_thresh = int(os.environ.get('SILENCE_THRESHOLD_DB', -40))
    return {
        "min_silence_len": min_silence_len,
        "padding": padding,
        "silence_thresh": silence_thresh,
    }


def split_file(audio_file, metadata, min_silence_len=None, padding=None, silence_thresh=None):
    metadata.clear()

    non_silent_segments = detect_pieces(audio_file, **split_params(min_silence_len, padding, silence_thresh))

    metadata.set_segments(non_silent_segments)
