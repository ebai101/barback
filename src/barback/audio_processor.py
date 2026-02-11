from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from pedalboard import Pedalboard, load_plugin


class AudioProcessor:
    def __init__(self):
        self.good_dither = self.load_goodhertz_plugin()

    def load_goodhertz_plugin(self):
        """Locate and load Goodhertz Good Dither plugin."""
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
                    return plugin
                except Exception as e:
                    print(f"Failed to load {path}: {e}")
                    continue
        print("Warning: Goodhertz Good Dither not found, using basic dithering")
        return None

    def fix_srbd(
        self,
        input_path: Path,
        target_sr: int = 44100,
        target_bits: int = 24,
    ) -> None:
        """
        Convert audio to target sample rate and bit depth.
        PRESERVES STEREO/MONO channel configuration.
        Deletes and recreates file to trigger file watcher.

        Args:
            input_path: Source audio file (will be deleted and recreated)
            target_sr: Target sample rate (default: 44100)
            target_bits: Target bit depth (default: 24)
        """
        # Load audio - always_2d=False means mono is 1D, stereo is 2D
        audio, sr = sf.read(input_path, always_2d=False)

        # Determine if stereo
        is_stereo = audio.ndim == 2

        # Resample if needed
        if sr != target_sr:
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
            audio = self.apply_goodhertz_dither(audio, sr, target_bits)
        else:
            audio = self.apply_basic_dither(audio, target_bits)

        # Write to temp file, delete original, rename
        temp_file = input_path.with_suffix(".tmp.wav")
        subtype_map = {16: "PCM_16", 24: "PCM_24", 32: "PCM_32"}
        sf.write(temp_file, audio, sr, subtype=subtype_map.get(target_bits, "PCM_24"))
        input_path.unlink()
        temp_file.rename(input_path)

    def apply_microfades(
        self,
        input_path: Path,
        fadein_samples: int = 35,
        fadeout_samples: int = 90,
    ) -> None:
        """
        Apply linear microfades to beginning and end of audio file.
        PRESERVES STEREO/MONO channel configuration.
        Deletes and recreates file to trigger file watcher.

        Args:
            input_path: Source audio file (will be deleted and recreated)
            fadein_samples: Number of samples for fade in (default: 35)
            fadeout_samples: Number of samples for fade out (default: 90)
        """
        # Load the audio file - preserves stereo/mono
        audio, sr = sf.read(input_path, always_2d=False)

        # Get file info to preserve bit depth
        info = sf.info(input_path)
        subtype = info.subtype

        # Determine if stereo
        is_stereo = audio.ndim == 2

        # Get total samples
        total_samples = len(audio)

        # Ensure fades don't exceed 25% of file length each
        max_fade = total_samples // 4
        fadein_samples = min(fadein_samples, max_fade)
        fadeout_samples = min(fadeout_samples, max_fade)

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

        # Write to temp file, delete original, rename
        temp_file = input_path.with_suffix(".tmp.wav")
        sf.write(temp_file, audio, sr, subtype=subtype)
        input_path.unlink()
        temp_file.rename(input_path)

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
