from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from pedalboard import Pedalboard, load_plugin

from barback.util.logger import get_logger


class AudioProcessor:
    def __init__(self):
        self.logger = get_logger()
        self.good_dither = self.load_goodhertz_plugin()

    def load_goodhertz_plugin(self):
        """Locate and load Goodhertz Good Dither plugin."""
        self.logger.info("Attempting to load Goodhertz Good Dither plugin")

        possible_paths = [
            "/Library/Audio/Plug-Ins/VST3/Ghz Good Dither 3.vst3",
            "~/Library/Audio/Plug-Ins/VST3/Ghz Good Dither 3.vst3",
            "/Library/Audio/Plug-Ins/Components/Ghz Good Dither 3.component",
            "~/Library/Audio/Plug-Ins/Components/Ghz Good Dither 3.component",
        ]
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
        input_path: Path,
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
            f"Starting SRBD fix: {input_path.name} -> {target_sr}Hz, {target_bits}bit",
            extra={
                "filepath": input_path,
                "target_sr": target_sr,
                "target_bits": target_bits,
            },
        )

        # Load audio
        audio, sr = sf.read(input_path, always_2d=False)
        original_sr = sr
        is_stereo = audio.ndim == 2
        self.logger.debug(f"Loaded {input_path.name}: {sr}Hz, shape={audio.shape}")

        # Resample if needed
        if sr != target_sr:
            self.logger.debug(f"Resampling {input_path.name}: {sr}Hz -> {target_sr}Hz")
            if is_stereo:
                # Resample each channel separately
                audio = np.column_stack(
                    [
                        librosa.resample(
                            audio[:, ch],
                            orig_sr=sr,
                            target_sr=target_sr,
                            res_type="kaiser_best",
                        )
                        for ch in range(audio.shape[1])
                    ]
                )
            else:
                # Mono - resample directly
                audio = librosa.resample(
                    audio, orig_sr=sr, target_sr=target_sr, res_type="kaiser_best"
                )
            sr = target_sr

        # Apply dithering
        if self.good_dither is not None:
            self.logger.debug(f"Applying Goodhertz dither to {input_path.name}")
            audio = self.apply_goodhertz_dither(audio, sr, target_bits)
        else:
            self.logger.debug(f"Applying basic dither to {input_path.name}")
            audio = self.apply_basic_dither(audio, target_bits)

        # Write to temp file, delete original, rename
        temp_file = input_path.with_suffix(".tmp.wav")
        subtype_map = {16: "PCM_16", 24: "PCM_24", 32: "PCM_32"}

        self.logger.debug(f"Writing processed audio to temp file: {temp_file}")
        sf.write(temp_file, audio, sr, subtype=subtype_map.get(target_bits, "PCM_24"))
        input_path.unlink()
        temp_file.rename(input_path)

        self.logger.info(
            f"Completed SRBD fix: {input_path.name}",
            extra={
                "filepath": input_path,
                "original_sr": original_sr,
                "new_sr": target_sr,
            },
        )

    def apply_microfades(
        self,
        input_path: Path,
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
            f"Starting microfade application: {input_path.name} (in={fadein_samples}, out={fadeout_samples})",
            extra={
                "filepath": input_path,
                "fadein_samples": fadein_samples,
                "fadeout_samples": fadeout_samples,
            },
        )

        # Load audio
        audio, sr = sf.read(input_path, always_2d=False)
        info = sf.info(input_path)
        subtype = info.subtype
        is_stereo = audio.ndim == 2
        total_samples = len(audio)

        # Ensure fades don't exceed 25% of file length each
        max_fade = total_samples // 4
        fadein_samples = min(fadein_samples, max_fade)
        fadeout_samples = min(fadeout_samples, max_fade)
        self.logger.debug(
            f"Applying fades: {fadein_samples}s in, {fadeout_samples} out"
        )

        # Apply fade in
        if fadein_samples > 0:
            fade_in_curve = np.linspace(0, 1, fadein_samples)
            if is_stereo:
                # Apply to both channels
                audio[:fadein_samples] *= fade_in_curve[:, np.newaxis]
            else:
                # Mono
                audio[:fadein_samples] *= fade_in_curve

        # Apply fade out
        if fadeout_samples > 0:
            fade_out_curve = np.linspace(1, 0, fadeout_samples)
            if is_stereo:
                # Apply to both channels
                audio[-fadeout_samples:] *= fade_out_curve[:, np.newaxis]
            else:
                # Mono
                audio[-fadeout_samples:] *= fade_out_curve

        temp_file = input_path.with_suffix(".tmp.wav")
        self.logger.debug(f"Writing processed audio to temp file: {temp_file}")
        sf.write(temp_file, audio, sr, subtype=subtype)
        input_path.unlink()
        temp_file.rename(input_path)

        self.logger.info(
            f"Completed microfade application: {input_path.name}",
            extra={"filepath": input_path},
        )

    def apply_goodhertz_dither(
        self, audio: np.ndarray, sr: int, target_bits: int
    ) -> np.ndarray:
        """
        Apply Goodhertz Good Dither plugin.
        Works with both mono and stereo.
        """
        board = Pedalboard([self.good_dither])
        processed = board(audio, sample_rate=sr)
        return processed

    def apply_basic_dither(self, audio: np.ndarray, target_bits: int) -> np.ndarray:
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
