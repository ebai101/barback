from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from enum import Enum
from multiprocessing import cpu_count
from pathlib import Path

import pandas as pd

Mode = Enum("Mode", ["FILES", "LOOPS", "DUPLICATES", "FINALIZER", "EXTENDER"])


@dataclass
class BarbackState:
    """Central state management for Barback."""

    audio_dir: Path
    selected_dir: Path

    mode: Mode = Mode.FILES
    audio_data: pd.DataFrame = pd.DataFrame(
        columns=[
            "File",
            "Duration",
            "Sample rate",
            "Bit depth",
            "Loop",
            "BPM",
            "Bars",
            "ZC",
        ]
    )
    duplicate_data: pd.DataFrame = pd.DataFrame(
        columns=["File", "File 2", "Similarity"]
    )
    finalizer_data: pd.DataFrame = pd.DataFrame(columns=["File", "Full Path", "Issues"])
    executor: ProcessPoolExecutor = ProcessPoolExecutor(max_workers=cpu_count())
    loaded: bool = False
