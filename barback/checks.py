import os
import re

import audio_file
import librosa
import numpy as np
import soundfile as sf


def check_loop(af: audio_file.AudioFile):
    af.load(mono=True)
    file, is_loop, bpm, num_bars = af.is_loop()
    zc = af.get_start_end_zero_crossing()
    af.unload()

    return file, is_loop, bpm, num_bars, zc


def find_duplicates_preproc(af: audio_file.AudioFile):
    af.load(sample_rate=22050, mono=True)
    if len(af.audio) < 1024:
        print(len(af.audio))
        pad_width = 1024 - len(af.audio)
        af.audio = np.pad(af.audio, (0, pad_width), mode="constant")

    af.zero_crossings = af.calc_zero_crossings()
    af.chroma = af.calc_chroma()
    af.spectral_contrast = af.calc_spectral_contrast()
    return af


def find_duplicates(afA: audio_file.AudioFile, afB: audio_file.AudioFile):
    if abs(afA.duration - afB.duration) > 0.1:
        return afA, afB, 0
    s = afA.weighted_similarity(afB)
    return s  # afA, afB, similarity


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
    result = []
    if "loops" not in af.filename and start >= 500:  # tighter restriction on one shots
        result.append(f"File {af.filename_to_link()} has {start} samples at the start")
    elif start >= 22050:
        result.append(f"File {af.filename_to_link()} has {start} samples at the start")
    if end >= 22050:
        result.append(f"File {af.filename_to_link()} has {end} samples at the end")

    if len(result) == 0:
        return ""
    elif len(result) == 1:
        return result[0]
    else:
        return "\n".join(result)


# no clicks/pops at start/end
def check_start_end_zero_crossing(af: audio_file.AudioFile):
    nonzeros = af.get_start_end_zero_crossing()
    if nonzeros != "":
        return f"File {af.filename_to_link()} has nonzero values at {nonzeros}"

    return ""


# loops are proper loops
def check_loops(af: audio_file.AudioFile):
    if "loops" not in af.filename:
        return ""
    file, is_loop, bpm, num_bars = af.is_loop()
    if "yes" not in is_loop:
        return f"File {af.filename_to_link()} does not loop"
    return ""


# tonal loops have key signature
def check_tonal_loop_key_signature(af: audio_file.AudioFile):
    # first check if there are multiple key signatures
    key_sig_regex = r"_[A-G][b#]?(maj|min)?"
    key_sig_matches = re.findall(key_sig_regex, os.path.basename(af.filename))
    if len(key_sig_matches) > 1:
        return f"File {af.filename_to_link()} has multiple key signatures"

    # then, if the file is a loop, check that the key signature is at the end
    if "loops" not in af.filename.lower():
        return ""
    key_sig_at_end_regex = r"^.*_[A-G](?:#|b)?(?:maj|min)?(?:\.wav)?$"
    if not re.match(key_sig_at_end_regex, os.path.basename(af.filename)) and not any(
        s in af.filename.lower() for s in ["drum", "perc", "hihat"]
    ):
        return f"File {af.filename_to_link()} does not have a key signature but is a tonal loop"
    return ""
