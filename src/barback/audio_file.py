import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from pedalboard.io import AudioFile as PedalboardAF

from barback.util.logger import get_logger
from barback.util.types import LoopResponse


@dataclass
class AudioFileError(Exception):
    message: str


class AudioFile:
    def __init__(self, file_path: Path):
        self.file_path: Path = Path(file_path)
        self.loaded: bool = False
        self.logger = get_logger()

    def load(self, sample_rate: float = 0, mono: bool = False) -> None:
        if self.loaded:
            self.logger.warning(
                f"Attempted to load already loaded file: {self.file_path}"
            )
            return

        if sample_rate == 0:
            sample_rate = self.sample_rate
        try:
            self.logger.debug(
                f"Loading audio file: {self.file_path.name} (sr={sample_rate}, mono={mono})"
            )
            self.audio, sr = librosa.load(self.file_path, sr=sample_rate, mono=mono)
        except Exception as e:
            self.logger.error(
                f"Failed to load audio file: {self.file_path.name}",
                extra={"filepath": self.file_path},
                exc_info=True,
            )
            raise AudioFileError(
                f"Unexpected error loading file {self.file_path}: {type(e).__name__}, {e}"
            )
        self.loaded = True

    def unload(self) -> None:
        if not self.loaded:
            self.logger.warning(
                f"Attempted to unload non-loaded file: {self.file_path}"
            )
            return

        self.logger.debug(f"Unloading audio file: {self.file_path.name}")
        del self.audio
        self.loaded = False

    def write(self, sr: int | float, bd: int, channels: int) -> None:
        """Writes AudioFile.audio to AudioFile.file_path.

        Args:
            sr: Sample rate, defaults to the sample rate of the file on disk
            subtype: Subtype string, defaults to the subtype of the file on disk
        """
        if not self.loaded:
            self.logger.warning(
                f"Attempted to write an unloaded audio file: {self.file_path}"
            )
            return

        self.logger.debug(f"Writing audio file... {self.file_path}")

        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", suffix=".wav", delete=False
            ) as temp_file:
                temp_path = Path(temp_file.name)
                with PedalboardAF(
                    temp_file.name,
                    "w",
                    samplerate=sr,
                    num_channels=channels,
                    bit_depth=bd,
                ) as f:  # ty:ignore[invalid-context-manager, no-matching-overload]
                    f.write(self.audio)
                self.logger.debug(f"Wrote audio to temp file at {temp_path}")
        except Exception as e:
            self.logger.error(f"Error writing audio file at {self.file_path}: {e}")

        try:
            shutil.move(temp_path, self.file_path)
            self.logger.info(
                f"Wrote audio file {self.file_path} (sr={sr}, bit_depth={bd}, channels={channels})"
            )
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            self.logger.error(f"Error replacing audio file at {self.file_path}: {e}")

    def __str__(self) -> str:
        return self.file_path.name

    @property
    def duration(self) -> float:
        return librosa.get_duration(path=self.file_path)

    @property
    def sample_rate(self) -> float:
        return librosa.get_samplerate(str(self.file_path))

    @property
    def subtype(self) -> str:
        return str(sf.info(self.file_path).subtype)

    @property
    def bit_depth(self) -> int:
        subtype_map = {
            "PCM_U8": 8,
            "PCM_16": 16,
            "PCM_24": 24,
            "PCM_32": 32,
            "FLOAT": 32,
            "DOUBLE": 64,
        }
        return subtype_map[self.subtype]

    @property
    def channels(self) -> int:
        return self.audio.ndim

    def is_loop(self) -> LoopResponse:
        if not self.loaded:
            raise AudioFileError(f"{self.file_path} is not loaded")

        total_samples = int(self.audio.shape[-1])
        bpm = None

        # Find BPM - return early if no valid BPM found
        bpm_regex = r"^(?:.*?_)?[A-Z]+[A-Z][a-zA-Z]*_(\d+)(?:_.*)?$"
        bpm_match = re.match(bpm_regex, self.file_path.name)
        if bpm_match:
            number = int(bpm_match.group(1))
            if 60 <= number <= 299:
                bpm = number

        # If BPM is not found in filename, try to infer it from file length
        inferred = False
        if bpm is None:
            for test_bars in [1, 2, 4, 8, 16, 32, 64]:
                len_minutes = total_samples / (self.sample_rate * 60)
                if len_minutes == 0:
                    continue
                test_bpm = (test_bars * 4) / len_minutes

                if 60 <= test_bpm <= 200 and abs(test_bpm - round(test_bpm)) < 0.05:
                    bpm = int(round(test_bpm))
                    inferred = True
                    break

            if bpm is None:
                return LoopResponse(
                    self.file_path,
                    False,
                    "no bpm found in name or inferred from length",
                )

        # Calculate samples/bar (assuming 4 beats/bar) and number of bars
        bar_len_samples = (self.sample_rate * 60 / bpm) * 4.0
        num_bars = total_samples / bar_len_samples
        num_bars_rounded = round(num_bars)

        if num_bars_rounded == 0:
            return LoopResponse(self.file_path, False, f"file too short for {bpm} bpm")

        expected_samples = num_bars_rounded * bar_len_samples
        target_samples = int(round(expected_samples))
        float_diff = abs(total_samples - expected_samples)

        # TODO: should be 1.0 still maybe
        is_loopable = float_diff < 100.0

        if is_loopable:
            msg = "yes" if not inferred else f"yes (inferred {bpm} bpm"
            return LoopResponse(
                self.file_path,
                True,
                msg,
                bpm,
                num_bars_rounded,
                bar_len_samples=bar_len_samples,
                expected_samples=expected_samples,
                target_samples=target_samples,
                sample_diff=float_diff,
            )

        suggestion_msg = f"off by {float_diff:.2f} samples"
        if not inferred:
            inferred_bpm = (num_bars_rounded * 4) / (
                total_samples / (self.sample_rate * 60)
            )
            if 60 <= inferred_bpm <= 299:
                if abs(inferred_bpm - round(inferred_bpm)) < 0.05:
                    suggestion_msg += f", suggested bpm: {int(round(inferred_bpm))}"

        return LoopResponse(
            self.file_path,
            False,
            suggestion_msg,
            bpm,
            num_bars_rounded,
            bar_len_samples=bar_len_samples,
            expected_samples=expected_samples,
            target_samples=target_samples,
            sample_diff=float_diff,
        )

    def get_start_end_zero_crossing(self, threshold: float = 0.02) -> str:
        if not self.loaded:
            raise AudioFileError(f"{self.file_path} is not loaded")
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
            raise AudioFileError(f"{self.file_path} is not loaded")
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
