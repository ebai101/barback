from pathlib import Path
from typing import Protocol, runtime_checkable

import pandas as pd
from textual.message import Message

from barback.audio_file import AudioFile


@runtime_checkable
class BarbackProtocol(Protocol):
    def info(self, message: str) -> None: ...
    def post_message(self, message: Message) -> bool: ...


def filter_df_by_dir(df: pd.DataFrame, dirname: Path) -> pd.DataFrame:
    return df[
        df.apply(
            lambda row: str(dirname) in str(row["File"].filename),
            axis=1,
        )
    ]


def get_valid_audio_files(dirname: Path) -> list[Path]:
    valid_extensions = (".mp3", ".flac", ".wav", ".aif", ".aiff")
    if dirname.is_dir():
        files = [
            file.absolute()
            for file in dirname.rglob("*")
            if file.is_file() and file.suffix.lower() in valid_extensions
        ]
        if not files:
            return []
        return files
    else:
        return []


def safe_absolute_path(row: pd.Series) -> str:
    if isinstance(row["File"], AudioFile):
        return str(row["File"].filename)
    elif isinstance(row["File"], str):
        return str(row["Full Path"])
    raise ValueError(f"No file path found in row {row}")
