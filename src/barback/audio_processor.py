from pathlib import Path

import librosa
import numpy as np
from pedalboard import Pedalboard, load_plugin

from barback.audio_file import AudioFile
from barback.util.logger import get_logger


class AudioProcessor:
    def __init__(self, good_dither_path: str | None = None):
        self.logger = get_logger()
        self.good_dither = self.load_goodhertz_plugin(good_dither_path)

    def load_goodhertz_plugin(self, provided_path: str | None):
        """Locate and load Goodhertz Good Dither plugin."""
        self.logger.info("Attempting to load Goodhertz Good Dither plugin")

        possible_paths = [
            "/Library/Audio/Plug-Ins/VST3/Ghz Good Dither 3.vst3",
            "~/Library/Audio/Plug-Ins/VST3/Ghz Good Dither 3.vst3",
            "/Library/Audio/Plug-Ins/Components/Ghz Good Dither 3.component",
            "~/Library/Audio/Plug-Ins/Components/Ghz Good Dither 3.component",
        ]
        if provided_path:
            possible_paths.insert(0, provided_path)

        for path_str in possible_paths:
            path = Path(path_str).expanduser()
            if path.exists():
                try:
                    plugin = load_plugin(str(path))
                    self.logger.info(f"Loaded Goodhertz Good Dither from: {path}")
                    return plugin
                except Exception as e:
                    self.logger.warning(f"Failed to load plugin from {path}: {e}")
                    continue
        self.logger.warning("Goodhertz Good Dither not found, using basic dithering")
        return None

    def fix_srbd(
        self,
        af: AudioFile,
        target_sr: int = 44100,
        target_bits: int = 24,
    ) -> None:
        """
        Convert audio to target sample rate and bit depth.

        Args:
            input_path: Source audio file (will be deleted and recreated)
            target_sr: Target sample rate (default: 44100)
            target_bits: Target bit depth (default: 24)
        """
        self.logger.info(
            f"Starting SR/BD fix: {af.file_path.name} -> {target_sr}Hz, {target_bits}bit",
            extra={
                "filepath": af,
                "target_sr": target_sr,
                "target_bits": target_bits,
            },
        )

        af.load()
        original_sr = af.sample_rate
        is_stereo = af.audio.ndim == 2
        self.logger.debug(
            f"Loaded {af.file_path.name}: {original_sr}Hz, shape={af.audio.shape}"
        )

        if af.sample_rate != target_sr:
            self.logger.debug(
                f"Resampling {af.file_path.name}: {original_sr}Hz -> {target_sr}Hz"
            )
            if is_stereo:
                # Resample each channel separately
                af.audio = np.column_stack(
                    [
                        librosa.resample(
                            af.audio[ch, :],
                            orig_sr=original_sr,
                            target_sr=target_sr,
                            res_type="kaiser_best",
                        )
                        for ch in range(af.audio.shape[0])
                    ]
                )
            else:
                # Mono - resample directly
                af.audio = librosa.resample(
                    af.audio,
                    orig_sr=original_sr,
                    target_sr=target_sr,
                    res_type="kaiser_best",
                )

        # Apply dithering
        if self.good_dither is not None:
            self.logger.debug(f"Applying Goodhertz dither to {af.file_path.name}")
            af.audio = self._apply_goodhertz_dither(af.audio, target_sr, target_bits)
        else:
            self.logger.debug(f"Applying basic dither to {af.file_path.name}")
            af.audio = self._apply_basic_dither(af.audio, target_bits)

        subtype_map = {16: "PCM_16", 24: "PCM_24", 32: "PCM_32"}
        af.write(target_sr, subtype_map.get(target_bits, "PCM_24"))
        af.unload()

        self.logger.info(
            f"Completed SR/BD fix: {af.file_path.name}",
            extra={
                "filepath": af.file_path,
                "original_sr": original_sr,
                "new_sr": target_sr,
            },
        )

    def apply_microfades(
        self,
        af: AudioFile,
        fadein_samples: int = 35,
        fadeout_samples: int = 90,
    ) -> None:
        """
        Apply linear microfades to beginning and end of audio file.

        Args:
            input_path: Source audio file (will be deleted and recreated)
            fadein_samples: Number of samples for fade in (default: 35)
            fadeout_samples: Number of samples for fade out (default: 90)
        """
        self.logger.info(
            f"Starting microfade application: {af.file_path.name} (in={fadein_samples}, out={fadeout_samples})",
            extra={
                "filepath": af,
                "fadein_samples": fadein_samples,
                "fadeout_samples": fadeout_samples,
            },
        )

        af.load()
        is_stereo = af.audio.ndim == 2

        self.logger.debug(
            f"Applying fades: {fadein_samples}s in, {fadeout_samples} out"
        )

        # Apply fade in
        if fadein_samples > 0:
            fadein_curve = np.linspace(0, 1, fadein_samples)
            if is_stereo:
                af.audio[:, :fadein_samples] *= fadein_curve
            else:
                af.audio[:, :fadein_samples] *= fadein_curve

        # Apply fade out
        if fadeout_samples > 0:
            fadeout_curve = np.linspace(1, 0, fadeout_samples)
            if is_stereo:
                af.audio[:, -fadeout_samples:] *= fadeout_curve
            else:
                af.audio[-fadeout_samples:] *= fadeout_curve

        af.write()
        af.unload()

        self.logger.info(
            f"Completed microfade application: {af.file_path.name}",
            extra={"filepath": af.file_path},
        )

    def _apply_goodhertz_dither(
        self, audio: np.ndarray, sr: int, target_bits: int
    ) -> np.ndarray:
        """
        Apply Goodhertz Good Dither plugin.
        Works with both mono and stereo.
        """
        board = Pedalboard([self.good_dither])
        processed = board(audio, sample_rate=sr)
        return processed

    def _apply_basic_dither(self, audio: np.ndarray, target_bits: int) -> np.ndarray:
        """
        Fallback TPDF (Triangular PDF) dithering.
        Works with both mono and stereo.

        Args:
            audio: Audio array (mono or stereo)
            target_bits: Target bit depth
        """
        q_step = 2.0 / (2**target_bits)
        dither = np.random.triangular(-q_step, 0, q_step, size=audio.shape)
        dithered = audio + dither
        quantized = np.round(dithered / q_step) * q_step
        return np.clip(quantized, -1.0, 1.0)

    def _apply_fade_out(self, audio: np.ndarray, fadeout_samples: int) -> np.ndarray:
        if fadeout_samples <= 0:
            return audio

        n = int(audio.shape[-1])
        n_fade = min(fadeout_samples, n)
        if n_fade <= 0:
            return audio

        curve = np.linspace(1.0, 0.0, n_fade, dtype=audio.dtype)
        audio[..., -n_fade:] *= curve
        return audio

    def _pad_to_length(self, audio: np.ndarray, target_samples: int) -> np.ndarray:
        current = int(audio.shape[-1])
        pad = target_samples - current
        if pad <= 0:
            return audio

        if audio.ndim == 1:
            return np.pad(audio, (0, pad), mode="constant")
        return np.pad(audio, ((0, 0), (0, pad)), mode="constant")

    def fix_loop(self, af: AudioFile, fadeout_samples: int = 90) -> str:
        """
        Fix small loop length errors by trimming or padding to the nearest integer
        target length (derived from BPM + rounded bars).

        Returns:
            "" if a fix was applied and written,
            otherwise a non-empty string describing why it was skipped.
        """
        self.logger.info(
            f"Starting loop fix: {af.file_path.name}",
            extra={"filepath": af, "operation": "fix_loop"},
        )

        af.load()
        try:
            resp = af.is_loop()

            if (
                resp.bpm is None
                or resp.bar_len_samples is None
                or resp.target_samples is None
            ):
                return f"Skipped loop fix for {af.file_path.name}: {resp.response}"

            current_samples = int(af.audio.shape[-1])
            target_samples = int(resp.target_samples)

            beat_len_samples = float(resp.bar_len_samples) * 0.25
            diff_samples = abs(current_samples - target_samples)

            if diff_samples >= beat_len_samples:
                return (
                    f"Skipped loop fix for {af.file_path.name}: "
                    f"off by {diff_samples:.0f} samples (>= 1 beat)"
                )

            if current_samples == target_samples:
                return f"Skipped loop fix for {af.file_path.name}: already at target length"

            if current_samples > target_samples:
                # Too long: truncate excess samples, then fade out
                af.audio = af.audio[..., :target_samples]
                af.audio = self._apply_fade_out(af.audio, fadeout_samples)
            else:
                # Too short: fade out first, then pad with silence
                af.audio = self._apply_fade_out(af.audio, fadeout_samples)
                af.audio = self._pad_to_length(af.audio, target_samples)

            af.write()
            return ""

        finally:
            af.unload()
