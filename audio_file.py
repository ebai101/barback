import logging
import os
import re
import urllib

import librosa
import numpy as np
import pywt
import soundfile as sf


# set to false to disable filename links if using a terminal that does not support them
create_filename_links = True


# applies fades of a given type
def fade(buf, fade_dir, fade_type):
    if fade_dir not in ["in", "out"]:
        raise ValueError('fade_dir must be "in" or "out"')

    match fade_type:
        case "linear":
            fade = np.linspace(0, 1, len(buf))
        case "cosine":
            fade = 0.5 * np.cos(np.pi * np.linspace(1, 0, len(buf))) + 0.5
        case _:
            raise ValueError("unsupported fade_type")

    if fade_dir == "out":
        return buf * fade[::-1]
    return buf * fade


class AudioFile:
    def __init__(self, filename, sample_rate=22050, mono=True, bpm=120):
        self.filename = filename
        self.sample_rate = sample_rate
        self.zero_crossings = None
        self.chroma = None
        self.spectral_contrast = None
        self.bpm = bpm

        try:
            self.audio, sr = librosa.load(self.filename, sr=self.sample_rate, mono=mono)
            if self.sample_rate == None:
                self.sample_rate = sr
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

    def calc_first_onset(self):
        onsets = librosa.onset.onset_detect(
            y=librosa.to_mono(self.audio), sr=self.sample_rate, units="samples"
        )
        return onsets[0]

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
        # find bpm - return early if none found
        bpm_regex = re.search("([6-9][0-9](?![0-9])|[1-2][0-9][0-9])", self.filename)
        if bpm_regex is None:
            return self, "no bpm found", "", ""
        else:
            bpm = int(bpm_regex.group(0))

        # calculate samples/bar (assuming 4 beats/bar) and number of bars
        bar_len_samples = self.sample_rate * ((60 / bpm) * 4.0)
        total_samples = self.audio.shape[0]
        num_bars = total_samples / bar_len_samples
        num_bars_rounded = round(num_bars)  # ideal bar length

        # check the file length against the expected value
        expected_samples = num_bars_rounded * bar_len_samples
        difference = abs(total_samples - expected_samples)
        is_loopable = difference <= 1.0

        if is_loopable:
            return self, "yes", bpm, num_bars_rounded
        else:
            return (
                self,
                f"no (off by {difference:.2f} samples)",
                bpm,
                num_bars_rounded,
            )

    def start_end_zero_crossing(self, threshold=0.02):
        if len(self.audio.shape) > 1:
            start_non_zero = any(abs(s) > threshold for s in self.audio[0])
            end_non_zero = any(abs(s) > threshold for s in self.audio[-1])
        else:
            start_non_zero = abs(self.audio[0]) > threshold
            end_non_zero = abs(self.audio[-1]) > threshold

        if start_non_zero and end_non_zero:
            return "start,end"
        elif start_non_zero:
            return "start"
        elif end_non_zero:
            return "end"
        else:
            return ""

    def extend(self, infer=False):
        bar_len_samples = round(self.sample_rate * ((60 / self.bpm) * 4.0))
        print(f"Bar length: {bar_len_samples}")
        print(f"First onset location: {self.first_onset}")
        if bar_len_samples < self.first_onset:
            new_bar_len = bar_len_samples
            while new_bar_len < self.first_onset:
                new_bar_len += bar_len_samples
            bar_len_samples = new_bar_len

        pad_len = bar_len_samples - self.first_onset
        print(f"Padding audio with {pad_len} samples")
        new_audio = np.ndarray(
            shape=(self.audio.shape[0], self.audio.shape[1] + pad_len), dtype=float
        )
        for i in range(new_audio.shape[0]):
            new_audio[i] = np.pad(self.audio[i], (pad_len, 0), "constant")
        self.audio = new_audio
        self.save()

    # perform smart fades on an audio object
    def smart_fade(self, threshold=0.02):
        audio_mono = librosa.to_mono(self.audio)
        test_len = 512  # length of the testing buffer
        test_c = int(test_len / 2)  # center index of the testing buffer
        fade_array = 2 ** np.arange(1, 9, 1)  # 2-256, each value is double the last

        for fl in fade_array:
            # test buffer is last test_c samples + first test_c samples
            test_buf = np.concatenate((audio_mono[-test_c:], audio_mono[:test_c]))

            # apply fade out and fade in
            test_buf[test_c - fl : test_c] = fade(
                test_buf[test_c - fl : test_c], "out", "cosine"
            )
            test_buf[test_c : test_c + fl] = fade(
                test_buf[test_c : test_c + fl], "in", "cosine"
            )

            cA, cD2, cD1 = pywt.wavedec(
                librosa.util.normalize(test_buf), "db1", level=2
            )  # wavelet decomposition
            detail = cD2[
                int(len(cD2) * 3 / 8) : int(len(cD2) * 5 / 8)
            ]  # only the center of the 2nd level is of interest
            detail *= librosa.filters.get_window(
                "parzen", len(detail)
            )  # window to avoid false positives on the edges

            if np.max(np.abs(detail)) < threshold:
                logging.info(f"fl of {fl} samples is long enough to prevent a click")

                # if stereo, fade both channels
                if len(self.audio.shape) > 1:
                    self.audio[0][-fl:] = fade(self.audio[0][-fl:], "out", "cosine")
                    self.audio[0][:fl] = fade(self.audio[0][:fl], "in", "cosine")
                    self.audio[1][-fl:] = fade(self.audio[1][-fl:], "out", "cosine")
                    self.audio[1][:fl] = fade(self.audio[1][:fl], "in", "cosine")
                else:
                    self.audio[-fl:] = fade(self.audio[-fl:], "out", "cosine")
                    self.audio[:fl] = fade(self.audio[:fl], "in", "cosine")
                return

        logging.info("no suitable fl found")

    def save(self):
        if len(self.audio.shape) > 1:
            sf.write(self.filename, self.audio.T, self.sample_rate, subtype="PCM_24")
        else:
            sf.write(self.filename, self.audio, self.sample_rate, subtype="PCM_24")

    def filename_to_link(self):
        label = os.path.basename(self.filename)
        if not create_filename_links:
            return label
        # Replace the UUID here with your own (see README.md)
        uri = "kmtrigger://macro=B7271B0E-F479-434F-986A-C688A41E144A&value={}".format(
            urllib.parse.quote(self.filename, safe="")
        )
        return f"\033]8;;{uri}\033\\{label}\033]8;;\033\\"
