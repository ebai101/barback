#!/usr/bin/env python3

import os
import re
import sys
import time
import urllib
import logging
import librosa
import warnings
import itertools
import numpy as np
from tqdm import tqdm
from tabulate import tabulate
from joblib import Parallel, delayed


class AudioFile:
    def __init__(self, filename, sample_rate=22050):
        self.filename = filename
        self.sample_rate = sample_rate
        self.zero_crossings = None
        self.chroma = None
        self.spectral_contrast = None

        try:
            self.audio, _ = librosa.load(self.filename, sr=self.sample_rate)
        except FileNotFoundError as e:
            logging.error(f"Error loading file: {e}")
        except Exception as e:
            logging.error(
                f"Unexpected error loading file {filename}: {type(e).__name__}, {e}"
            )

    def calc_zero_crossings(self):
        return np.mean(np.abs(np.diff(np.sign(self.audio))) > 0)

    def calc_chroma(self):
        return librosa.feature.chroma_cqt(y=self.audio, sr=self.sample_rate)

    def calc_spectral_contrast(self):
        return librosa.feature.spectral_contrast(y=self.audio, sr=self.sample_rate)

    def weighted_similarity(self, target):
        # zero crossing
        zcr_similarity = 1 - np.abs(self.zero_crossings - target.zero_crossings)

        # chroma
        chroma_min = min(self.chroma.shape[1], target.chroma.shape[1])
        chroma_similarity = 1 - np.mean(
            np.abs(self.chroma[:, :chroma_min] - target.chroma[:, :chroma_min])
        )

        # spectral contrast
        spectral_min = min(
            self.spectral_contrast.shape[1],
            target.spectral_contrast.shape[1],
        )
        spectral_similarity = np.mean(
            np.abs(
                self.spectral_contrast[:, :spectral_min]
                - target.spectral_contrast[:, :spectral_min]
            )
        )
        normalized_spectral_similarity = 1 - spectral_similarity / np.max(
            [
                np.abs(self.spectral_contrast[:, :spectral_min]),
                np.abs(target.spectral_contrast[:, :spectral_min]),
            ]
        )

        result = (
            zcr_similarity + chroma_similarity + normalized_spectral_similarity
        ) / 3

        return self, target, result

    # returns a boolean (loopable/not loopable) and an error message if no BPM is found
    def is_loop(self):
        # find bpm - return if none found
        bpm_regex = re.search("([6-9][0-9](?![0-9])|[1-2][0-9][0-9])", self.filename)
        if bpm_regex is None:
            return self, "no bpm found", "", ""
        else:
            bpm = int(bpm_regex.group(0))

        # calculate samples/bar (assuming 4 beats/bar) and number of bars
        bar_len_samples = self.sample_rate * ((60 / bpm) * 4.0)
        num_bars = self.audio.shape[0] / bar_len_samples
        num_bars = round(num_bars)  # ideal bar length

        # sample is considered loopable if the remainder is within a whole sample
        remainder = self.audio.shape[0] % bar_len_samples
        if self.audio.shape[0] < (num_bars * bar_len_samples):
            remainder = self.audio.shape[0] - (num_bars * bar_len_samples)
        is_loopable = -1.0 < remainder < 1.0

        if is_loopable:
            return self, "yes", bpm, num_bars
        else:
            return self, "no", bpm, num_bars

    def filename_to_link(self):
        label = os.path.basename(self.filename)
        # Replace the UUID here with your own (see README.md)
        uri = "kmtrigger://macro=B7271B0E-F479-434F-986A-C688A41E144A&value={}".format(
            urllib.parse.quote(self.filename, safe="")
        )
        return f"\033]8;;{uri}\033\\{label}\033]8;;\033\\"


# finds valid audio files in a directory
def validate_audio_files(audio_dir):
    valid_extensions = (".mp3", ".flac", ".wav", ".aif")
    if os.path.isdir(audio_dir):
        try:
            files = [
                os.path.join(audio_dir, f)
                for f in os.listdir(audio_dir)
                if f.endswith(valid_extensions)
            ]
        except FileNotFoundError as e:
            logging.error(f"Error opening file: {e}")
            return None
    else:
        logging.error("Must specify a directory")
        return None

    return files


def find_loops_main(audio_files):
    # preprocessing
    audios = [
        r
        for r in tqdm(
            Parallel(return_as="generator", n_jobs=-1)(
                delayed(AudioFile)(f) for f in audio_files
            ),
            total=len(audio_files),
            desc="Preprocessing",
        )
    ]

    # check for loops
    def _proc(a):
        res = a.is_loop()
        # print(res)
        return res

    result = [
        r
        for r in tqdm(
            Parallel(return_as="generator", n_jobs=-1)(
                delayed(_proc)(c) for c in audios
            ),
            total=len(audios),
            desc="Checking for loops",
        )
    ]
    loops = sorted(
        [(r[0].filename_to_link(), r[1], r[2], r[3]) for r in result if r[1]],
        key=lambda x: x[0],
    )
    print(tabulate(loops, headers=["file", "is_loop", "bpm", "num_bars"]))


def find_duplicates_main(audio_files):
    # preprocessing
    def _preproc(f):
        warnings.filterwarnings("ignore", category=UserWarning, module="librosa")
        a = AudioFile(f)
        a.zero_crossings = a.calc_zero_crossings()
        a.chroma = a.calc_chroma()
        a.spectral_contrast = a.calc_spectral_contrast()
        return a

    audios = [
        r
        for r in tqdm(
            Parallel(return_as="generator", n_jobs=-1)(
                delayed(_preproc)(f) for f in audio_files
            ),
            total=len(audio_files),
            desc="Preprocessing",
        )
    ]

    # create list of comparison combinations, to avoid redundant checks
    combinations = list(
        (i, j) for ((i, _), (j, _)) in itertools.combinations(enumerate(audios), 2)
    )

    # check similarity
    def _proc(c):
        s = audios[c[0]].weighted_similarity(audios[c[1]])
        # print(s)
        return s

    result = [
        r
        for r in tqdm(
            Parallel(return_as="generator", n_jobs=-1)(
                delayed(_proc)(c) for c in combinations
            ),
            total=len(combinations),
            desc="Checking similarity",
        )
    ]

    likely_dupes = sorted(
        [
            (r[0].filename_to_link(), r[1].filename_to_link(), r[2])
            for r in result
            if r[2] > 0.99
        ],
        key=lambda x: x[2],
        reverse=True,
    )
    possible_dupes = sorted(
        [
            (r[0].filename_to_link(), r[1].filename_to_link(), r[2])
            for r in result
            if r[2] > 0.9 and r[2] < 0.99
        ],
        key=lambda x: x[2],
        reverse=True,
    )

    if len(likely_dupes) > 0:
        print("\nLikely Duplicates:")
        print(tabulate(likely_dupes, headers=["file 1", "file 2", "similarity"]))
    if len(possible_dupes) > 0:
        print("\nPossible Duplicates:")
        print(tabulate(possible_dupes, headers=["file 1", "file 2", "similarity"]))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("specify an action and a folder")
        sys.exit(1)
    action = sys.argv[1]
    audio_dir = os.path.abspath(sys.argv[2])

    start_time = time.time()

    audio_files = validate_audio_files(audio_dir)
    if action == "duplicates":
        find_duplicates_main(audio_files)
    elif action == "loops":
        find_loops_main(audio_files)

    end_time = time.time() - start_time
    print(f"done in {end_time} sec")
