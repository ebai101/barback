import re
import os
import urllib
import logging
import librosa
import numpy as np


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
        is_loopable = -1.0 <= remainder <= 1.0

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
