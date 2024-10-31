import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import librosa
import numpy as np
import soundfile as sf
from numpy.typing import NDArray
from typing_extensions import Self

# applies fades of a given type
# def fade(buf, fade_dir, fade_type):
#     if fade_dir not in ["in", "out"]:
#         raise ValueError('fade_dir must be "in" or "out"')

#     match fade_type:
#         case "linear":
#             fade = np.linspace(0, 1, len(buf))
#         case "cosine":
#             fade = 0.5 * np.cos(np.pi * np.linspace(1, 0, len(buf))) + 0.5
#         case _:
#             raise ValueError("unsupported fade_type")

#     if fade_dir == "out":
#         return buf * fade[::-1]
#     return buf * fade


@dataclass
class AudioFileError(Exception):
    message: str


@dataclass
class IsLoopResponse:
    filename: Path
    is_loop: bool
    response: str
    bpm: Optional[int] = None
    num_bars: Optional[int] = None


class AudioFile:

    def __init__(self, filename: Path):
        self.filename = filename
        self.sample_rate = librosa.get_samplerate(self.filename)
        self.bit_depth = sf.info(self.filename).subtype
        self.duration = librosa.get_duration(path=self.filename)
        self.loaded = False

    def load(self, sample_rate: float = 0, mono: bool = False) -> None:
        if self.loaded:
            raise AudioFileError(f"Tried to load already loaded file {self.filename}")
        if sample_rate == 0:
            sample_rate = self.sample_rate
        try:
            self.audio, sr = librosa.load(self.filename, sr=sample_rate, mono=mono)
        except Exception as e:
            raise AudioFileError(
                f"Unexpected error loading file {self.filename}: {type(e).__name__}, {e}"
            )
        self.loaded = True

    def unload(self) -> None:
        if not self.loaded:
            raise AudioFileError(
                f"Tried to unload non-loaded audio file {self.filename}"
            )
        del self.audio
        self.loaded = False

    def __str__(self) -> str:
        return os.path.basename(self.filename)

    def calc_zero_crossings(self) -> float:
        if not hasattr(self, "audio"):
            raise AudioFileError(f"{self.filename} is not loaded")
        return float(np.mean(np.abs(np.diff(np.sign(self.audio))) > 0))

    def calc_chroma(self) -> NDArray[np.float32]:
        if not hasattr(self, "audio"):
            raise AudioFileError(f"{self.filename} is not loaded")
        return librosa.feature.chroma_cqt(y=self.audio, sr=self.sample_rate)

    def calc_spectral_contrast(self) -> NDArray[np.float32]:
        if not hasattr(self, "audio"):
            raise AudioFileError(f"{self.filename} is not loaded")
        return librosa.feature.spectral_contrast(y=self.audio, sr=self.sample_rate)

    def calc_first_onset(self) -> int:
        if not hasattr(self, "audio"):
            raise AudioFileError(f"{self.filename} is not loaded")
        onsets = librosa.onset.onset_detect(
            y=librosa.to_mono(self.audio), sr=self.sample_rate, units="samples"
        )
        return int(onsets[0])

    def weighted_similarity(self, target: Self) -> Tuple[str, str, float]:
        if not hasattr(self, "zero_crossings"):
            self.zero_crossings = self.calc_zero_crossings()
        if not hasattr(self, "chroma"):
            self.chroma = self.calc_chroma()
        if not hasattr(self, "spectral_contrast"):
            self.spectral_contrast = self.calc_spectral_contrast()

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
            float(zcr_similarity + chroma_similarity + normalized_spectral_similarity)
            / 3
        )

        return self.filename.name, target.filename.name, result

    # returns a boolean (loopable/not loopable) and an error message if no BPM is found
    def is_loop(self) -> IsLoopResponse:
        if not hasattr(self, "audio"):
            raise AudioFileError(f"{self.filename} is not loaded")
        # find bpm - return early if no valid bpm found
        bpm_regex = r"^(?:.*?_)?[A-Z]+[A-Z][a-zA-Z]*_(\d+)(?:_.*)?$"
        bpm_match = re.match(bpm_regex, os.path.basename(self.filename))
        if bpm_match:
            number = int(bpm_match.group(1))
            if 60 <= number <= 299:
                bpm = number
            else:
                return IsLoopResponse(self.filename, False, "bpm out of range")
        else:
            return IsLoopResponse(self.filename, False, "no bpm found")

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
            return IsLoopResponse(self.filename, True, "yes", bpm, num_bars_rounded)
        else:
            return IsLoopResponse(
                self.filename,
                False,
                f"no (off by {difference:.2f} samples)",
                bpm,
                num_bars_rounded,
            )

    def get_start_end_zero_crossing(self, threshold: float = 0.02) -> str:
        if not hasattr(self, "audio"):
            raise AudioFileError(f"{self.filename} is not loaded")
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

    # def extend(self, infer=False):
    #     bar_len_samples = round(self.sample_rate * ((60 / self.bpm) * 4.0))
    #     print(f"Bar length: {bar_len_samples}")
    #     print(f"First onset location: {self.first_onset}")
    #     if bar_len_samples < self.first_onset:
    #         new_bar_len = bar_len_samples
    #         while new_bar_len < self.first_onset:
    #             new_bar_len += bar_len_samples
    #         bar_len_samples = new_bar_len

    #     pad_len = bar_len_samples - self.first_onset
    #     print(f"Padding audio with {pad_len} samples")
    #     new_audio = np.ndarray(
    #         shape=(self.audio.shape[0], self.audio.shape[1] + pad_len), dtype=float
    #     )
    #     for i in range(new_audio.shape[0]):
    #         new_audio[i] = np.pad(self.audio[i], (pad_len, 0), "constant")
    #     self.audio = new_audio
    #     self.save()

    def get_start_end_silence(self) -> Tuple[float, float]:
        if not hasattr(self, "audio"):
            raise AudioFileError(f"{self.filename} is not loaded")
        audio_mono = librosa.to_mono(self.audio)
        audio_mono_trim, index = librosa.effects.trim(audio_mono, top_db=75)
        if librosa.get_duration(
            y=audio_mono, sr=self.sample_rate
        ) == librosa.get_duration(y=audio_mono_trim, sr=self.sample_rate):
            return 0, 0
        else:
            start = 0
            end = 0
            if index[0] > 0:
                start = index[0]
            if index[1] != len(audio_mono):
                end = len(audio_mono) - index[1]
            return start, end

    def save(self) -> None:
        if not hasattr(self, "audio"):
            raise AudioFileError(f"{self.filename} is not loaded")
        if len(self.audio.shape) > 1:
            sf.write(self.filename, self.audio.T, self.sample_rate, subtype="PCM_24")
        else:
            sf.write(self.filename, self.audio, self.sample_rate, subtype="PCM_24")

    def _get_sort_key(self) -> Tuple[int, str | int]:
        filename = str(self.filename.name)
        match = re.search(r"^(?:.*?_)?[A-Z]+[A-Z][a-zA-Z]*_(\d+)(?:_.*)?$", filename)
        if match:
            return (0, int(match.group(1)))
        else:
            return (1, filename)

    def __lt__(self, other: Self) -> bool:
        return self._get_sort_key() < other._get_sort_key()

    def __gt__(self, other: Self) -> bool:
        return self._get_sort_key() > other._get_sort_key()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AudioFile):
            return NotImplemented
        return self._get_sort_key() == other._get_sort_key()

    def __le__(self, other: Self) -> bool:
        return self._get_sort_key() <= other._get_sort_key()

    def __ge__(self, other: Self) -> bool:
        return self._get_sort_key() >= other._get_sort_key()

    def __ne__(self, other: object) -> bool:
        if not isinstance(other, AudioFile):
            return NotImplemented
        return self._get_sort_key() != other._get_sort_key()
