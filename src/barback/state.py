from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from enum import Enum
from multiprocessing import cpu_count
from pathlib import Path

from barback.audio_data import AudioData

Mode = Enum("Mode", ["FILES", "LOOPS", "DUPLICATES", "FINALIZER", "EXTENDER"])


@dataclass
class BarbackState:
    audio_dir: Path
    selected_dir: Path

    audio_data: AudioData = AudioData()
    mode: Mode = Mode.FILES
    executor: ProcessPoolExecutor = ProcessPoolExecutor(max_workers=cpu_count())
    loaded: bool = False
