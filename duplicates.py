#!/usr/bin/env python3

import os
import sys
import time
import logging
import urllib
import librosa
import warnings
import itertools
import numpy as np
from tqdm import tqdm
from tabulate import tabulate
from joblib import Parallel, delayed


class AudioFile:
    def __init__(self, filename, sample_rate=22050):
        warnings.filterwarnings("ignore", category=UserWarning, module="librosa")

        self.filename = filename
        self.sample_rate = sample_rate

        try:
            self.audio, _ = librosa.load(self.filename, sr=self.sample_rate)
        except FileNotFoundError as e:
            logging.error(f"Error loading file: {e}")
        except Exception as e:
            logging.error(
                f"Unexpected error loading file {filename}: {type(e).__name__}, {e}"
            )

        self.zero_crossings = self.get_zero_crossings()
        # self.onset_vector = self.get_onset_vector()
        self.chroma = self.get_chroma()
        self.spectral_contrast = self.get_spectral_contrast()

    def get_zero_crossings(self):
        return np.mean(np.abs(np.diff(np.sign(self.audio))) > 0)

    def get_onset_vector(self):
        onset_vector = np.zeros(len(self.audio))
        onsets = librosa.onset.onset_detect(
            y=self.audio, sr=self.sample_rate, units="time"
        )
        onsets = np.array(onsets) * self.sample_rate
        onset_vector[onsets.astype(int)] = 1

    def get_chroma(self):
        return librosa.feature.chroma_cqt(y=self.audio, sr=self.sample_rate)

    def get_spectral_contrast(self):
        return librosa.feature.spectral_contrast(y=self.audio, sr=self.sample_rate)


def load_files(audio_dir):
    audios = []
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
        logging.error("must specify a directory")
        return None

    # this is actually hindered by joblib parallelization, so it's disabled for now
    # probably due to internal librosa caching/memoization
    audios = [
        audio
        for audio in tqdm(
            Parallel(return_as="generator", n_jobs=-1)(
                delayed(AudioFile)(file) for file in files
            ),
            total=len(files),
            desc="Loading files",
        )
    ]

    return audios


def weighted_similarity(audio_files):
    # zero crossing
    zcr_similarity = 1 - np.abs(
        audio_files[0].zero_crossings - audio_files[1].zero_crossings
    )

    # chroma
    chroma_min = min(audio_files[0].chroma.shape[1], audio_files[1].chroma.shape[1])
    chroma_similarity = 1 - np.mean(
        np.abs(
            audio_files[0].chroma[:, :chroma_min]
            - audio_files[1].chroma[:, :chroma_min]
        )
    )

    # spectral contrast
    spectral_min = min(
        audio_files[0].spectral_contrast.shape[1],
        audio_files[1].spectral_contrast.shape[1],
    )
    spectral_similarity = np.mean(
        np.abs(
            audio_files[0].spectral_contrast[:, :spectral_min]
            - audio_files[1].spectral_contrast[:, :spectral_min]
        )
    )
    normalized_spectral_similarity = 1 - spectral_similarity / np.max(
        [
            np.abs(audio_files[0].spectral_contrast[:, :spectral_min]),
            np.abs(audio_files[1].spectral_contrast[:, :spectral_min]),
        ]
    )

    result = (zcr_similarity + chroma_similarity + normalized_spectral_similarity) / 3

    return (audio_files[0].filename, audio_files[1].filename, result)


def filename_to_link(filename):
    label = os.path.basename(filename)
    # Replace the UUID here with your own (see README.md)
    uri = "kmtrigger://macro=B7271B0E-F479-434F-986A-C688A41E144A&value={}".format(
        urllib.parse.quote(filename, safe="")
    )
    return f"\033]8;;{uri}\033\\{label}\033]8;;\033\\"


def main():
    if len(sys.argv) < 2:
        print("specify a folder")
        sys.exit(1)
    else:
        audio_dir = os.path.abspath(sys.argv[1])

    start_time = time.time()
    audios = load_files(audio_dir)
    combinations = list(
        (i, j) for ((i, _), (j, _)) in itertools.combinations(enumerate(audios), 2)
    )
    result = [
        r
        for r in tqdm(
            [weighted_similarity((audios[c[0]], audios[c[1]])) for c in combinations],
            total=len(combinations),
            desc="Processing",
        )
    ]
    parallel_time = time.time() - start_time
    print(f"done in {parallel_time} sec")

    likely_dupes = sorted(
        [
            (filename_to_link(r[0]), filename_to_link(r[1]), r[2])
            for r in result
            if r[2] > 0.99
        ],
        key=lambda x: x[2],
        reverse=True,
    )
    possible_dupes = sorted(
        [
            (filename_to_link(r[0]), filename_to_link(r[1]), r[2])
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
    main()
