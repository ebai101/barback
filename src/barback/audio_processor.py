from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from pedalboard import Pedalboard, load_plugin


class AudioProcessor:
    def __init__(self):
        self.good_dither = self._load_goodhertz_plugin()

    def _load_goodhertz_plugin(self):
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

    def fix_samplerate_and_bitdepth(
        self, input_path: Path, target_sr: int = 44100, target_bits: int = 24
    ) -> None:
        """
        Convert audio to target samplerate and bit depth by DELETE + RECREATE.
        Mimics behavior of Myriad/RX to trigger file watcher properly.

        Args:
            input_path: Source audio file (will be deleted and recreated)
            target_sr: Target sample rate (default: 44100)
            target_bits: Target bit depth (default: 24)
        """
        audio, sr = sf.read(input_path, always_2d=False)

        if sr != target_sr:
            audio = librosa.resample(
                audio, orig_sr=sr, target_sr=target_sr, res_type="kaiser_best"
            )
            sr = target_sr

        if self.good_dither is not None:
            audio = self._apply_goodhertz_dither(audio, sr, target_bits)
        else:
            audio = self._apply_basic_dither(audio, target_bits)

        temp_file = input_path.with_suffix(".tmp.wav")
        subtype_map = {16: "PCM_16", 24: "PCM_24", 32: "PCM_32"}
        sf.write(temp_file, audio, sr, subtype=subtype_map.get(target_bits, "PCM_24"))
        input_path.unlink()
        temp_file.rename(input_path)

    def _apply_goodhertz_dither(
        self, audio: np.ndarray, sr: int, target_bits: int
    ) -> np.ndarray:
        """Apply Goodhertz Good Dither plugin."""
        board = Pedalboard([self.good_dither])
        processed = board(audio, sample_rate=sr)
        return processed

    def _apply_basic_dither(self, audio: np.ndarray, target_bits: int) -> np.ndarray:
        """Fallback TPDF (Triangular PDF) dithering when Goodhertz unavailable."""
        q_step = 2.0 / (2**target_bits)
        dither = np.random.triangular(-q_step, 0, q_step, size=audio.shape)
        dithered = audio + dither
        quantized = np.round(dithered / q_step) * q_step
        return np.clip(quantized, -1.0, 1.0)
