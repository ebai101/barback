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


_BPM_IN_FILENAME = re.compile(r"^(?:.*?_)?[A-Z]+[A-Z][a-zA-Z]*_(\d+)(?:_.*)?$")


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
            self.audio, _ = librosa.load(self.file_path, sr=sample_rate, mono=mono)
        except Exception as e:
            self.logger.exception(
                f"Failed to load audio file: {self.file_path.name}",
                extra={"filepath": self.file_path},
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

    def write(self, sr: float, bd: int, channels: int) -> None:
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

    def is_loop(self, *, allow_inference: bool = True) -> LoopResponse:
        if not self.loaded:
            raise AudioFileError(f"{self.file_path} is not loaded")

        total_samples = int(self.audio.shape[-1])
        bpm = self._extract_filename_bpm()
        inferred = False

        if bpm is None and allow_inference:
            bpm = self._infer_loop_bpm(total_samples)
            inferred = bpm is not None

        if bpm is None:
            return LoopResponse(
                file_path=self.file_path,
                is_loop=False,
                response="no BPM found in filename or inferred from length",
            )

        bar_len_samples = (self.sample_rate * 60 / bpm) * 4.0
        num_bars = total_samples / bar_len_samples
        rounded_bars = round(num_bars)

        if rounded_bars == 0:
            return LoopResponse(
                file_path=self.file_path,
                is_loop=False,
                response=f"file too short for {bpm} BPM",
            )

        expected_samples = rounded_bars * bar_len_samples
        sample_diff = abs(total_samples - expected_samples)

        if sample_diff >= 1.0:
            return LoopResponse(
                file_path=self.file_path,
                is_loop=False,
                response=f"off by {sample_diff:.2f} samples",
                # Deliberately omit bpm and num_bars.
            )

        source = f"inferred {bpm} BPM" if inferred else f"{bpm} BPM from filename"
        return LoopResponse(
            file_path=self.file_path,
            is_loop=True,
            response=f"yes ({source})",
            bpm=bpm,
            num_bars=rounded_bars,
            bar_len_samples=bar_len_samples,
            expected_samples=expected_samples,
            target_samples=round(expected_samples),
            sample_diff=sample_diff,
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

    def _extract_filename_bpm(self) -> int | None:
        match = _BPM_IN_FILENAME.match(self.file_path.name)
        if match is None:
            return None

        bpm = int(match.group(1))
        return bpm if 60 <= bpm <= 299 else None

    def _infer_loop_bpm(self, total_samples: int) -> int | None:
        duration_minutes = total_samples / (self.sample_rate * 60)
        if duration_minutes <= 0:
            return None

        for bars in (1, 2, 4, 8, 16, 32, 64):
            candidate_bpm = (bars * 4) / duration_minutes
            if (
                60 <= candidate_bpm <= 200
                and abs(candidate_bpm - round(candidate_bpm)) < 0.05
            ):
                return round(candidate_bpm)

        return None
