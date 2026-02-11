import os
import re
from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from numpy.typing import NDArray

from barback.util.types import LoopResponse


@dataclass
class AudioFileError(Exception):
    message: str


class AudioFile:
    def __init__(self, filename: Path):
        self.filename: Path = Path(filename)
        self.loaded: bool = False

    @property
    def duration(self) -> float:
        return librosa.get_duration(path=self.filename)

    @property
    def sample_rate(self) -> float:
        return librosa.get_samplerate(str(self.filename))

    @property
    def bit_depth(self) -> str:
        return str(sf.info(self.filename).subtype)

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
        return self.filename.name

    @property
    def zero_crossings(self) -> float:
        if not self.loaded:
            raise AudioFileError(f"{self.filename} is not loaded")
        if not hasattr(self, "_zero_crossings"):
            self._zero_crossings = float(
                np.mean(np.abs(np.diff(np.sign(self.audio))) > 0)
            )
        return self._zero_crossings

    @property
    def chroma(self) -> NDArray[np.float32]:
        if not self.loaded:
            raise AudioFileError(f"{self.filename} is not loaded")
        if not hasattr(self, "_chroma"):
            self._chroma = librosa.feature.chroma_cqt(y=self.audio, sr=self.sample_rate)
        return self._chroma

    @property
    def spectral_contrast(self) -> NDArray[np.float32]:
        if not self.loaded:
            raise AudioFileError(f"{self.filename} is not loaded")
        if not hasattr(self, "_spectral_contrast"):
            self._spectral_contrast = librosa.feature.spectral_contrast(
                y=self.audio, sr=self.sample_rate
            )
        return self._spectral_contrast

    @property
    def first_onset(self) -> int:
        if not self.loaded:
            raise AudioFileError(f"{self.filename} is not loaded")
        if not hasattr(self, "_first_onset"):
            self._first_onset = int(
                librosa.onset.onset_detect(
                    y=librosa.to_mono(self.audio), sr=self.sample_rate, units="samples"
                )[0]
            )
        return self._first_onset

    def weighted_similarity(self, target: "AudioFile") -> tuple[str, str, float]:
        if not self.loaded:
            raise AudioFileError(f"{self.filename} is not loaded")

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
    def is_loop(self) -> LoopResponse:
        if not self.loaded:
            raise AudioFileError(f"{self.filename} is not loaded")
        # find bpm - return early if no valid bpm found
        bpm_regex = r"^(?:.*?_)?[A-Z]+[A-Z][a-zA-Z]*_(\d+)(?:_.*)?$"
        bpm_match = re.match(bpm_regex, os.path.basename(self.filename))
        if bpm_match:
            number = int(bpm_match.group(1))
            if 60 <= number <= 299:
                bpm = number
            else:
                return LoopResponse(self.filename, False, "bpm out of range")
        else:
            return LoopResponse(self.filename, False, "no bpm found")

        # calculate samples/bar (assuming 4 beats/bar) and number of bars
        bar_len_samples = self.sample_rate * ((60 / bpm) * 4.0)
        total_samples = self.audio.shape[0]
        num_bars = total_samples / bar_len_samples
        num_bars_rounded = round(num_bars)  # ideal bar length

        # check the file length against the expected value
        expected_samples = num_bars_rounded * bar_len_samples
        difference = abs(total_samples - expected_samples)
        is_loopable = difference < 1.0

        if is_loopable:
            return LoopResponse(self.filename, True, "yes", bpm, num_bars_rounded)
        else:
            return LoopResponse(
                self.filename,
                False,
                f"off by {difference:.2f} samples",
                bpm,
                num_bars_rounded,
            )

    def get_start_end_zero_crossing(self, threshold: float = 0.02) -> str:
        if not self.loaded:
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

    def get_start_end_silence(self) -> tuple[float, float]:
        if not self.loaded:
            raise AudioFileError(f"{self.filename} is not loaded")
        audio_mono = librosa.to_mono(self.audio)
        non_silent = librosa.effects._signal_to_frame_nonsilent(audio_mono, top_db=75)

        nonzero = np.flatnonzero(non_silent)

        if nonzero.size > 0:
            start = int(librosa.core.frames_to_samples(nonzero[0]))
            end = len(audio_mono) - min(
                audio_mono.shape[-1],
                int(librosa.core.frames_to_samples(nonzero[-1] + 1)),
            )
        else:
            start, end = 0, len(audio_mono)

        return start, end
