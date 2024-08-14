import os

import librosa
import numpy as np
import soundfile as sf

import audio_file


# wav, 44.1, 24 bit
def check_file_sr_bd(af: audio_file.AudioFile):
    extension = os.path.splitext(af.filename)[1].lower()
    if extension != ".wav":
        return f"File {af.filename_to_link()} is not a wav file"

    try:
        sr = librosa.get_samplerate(af.filename)
        with sf.SoundFile(af.filename) as f:
            bd = f.subtype
    except Exception as e:
        return f"Error processing {af.filename_to_link()}: {str(e)}"

    if sr != 44100:
        return f"File {af.filename_to_link()} sample rate {sr} is incorrect"

    if bd != "PCM_24":
        return f"File {af.filename_to_link()} bit depth {bd} is incorrect"

    return ""


# no extra silence at start/end
def check_silence(af: audio_file.AudioFile):
    start, end = af.get_start_end_silence()
    if start >= 22050:
        return f"File {af.filename_to_link()} has {start} samples at the start"
    if end >= 22050:
        return f"File {af.filename_to_link()} has {end} samples at the end"

    return ""


# no clicks/pops at start/end
def check_start_end_zero_crossing(af: audio_file.AudioFile):
    nonzeros = af.get_start_end_zero_crossing()
    if nonzeros != "":
        return f"File {af.filename_to_link()} has nonzero values at {nonzeros}"

    return ""


# loops are proper loops
def check_loops(af: audio_file.AudioFile):
    if not "loops" in af.filename:
        return ""
    file, is_loop, bpm, num_bars = af.is_loop()
    if not "yes" in is_loop:
        return f"File {af.filename_to_link()} does not loop"
    return ""


# normalized to -1dB
# def check_normalization(af: audio_file.AudioFile, tolerance=0.1):
#     audio_db = librosa.amplitude_to_db(np.abs(af.audio), ref=np.max)
#     peak_db = np.max(audio_db)
#     if not abs(peak_db + 1) <= tolerance:
#         return f"File {af.filename_to_link()} peaks at {peak_db}"

#     return ""
