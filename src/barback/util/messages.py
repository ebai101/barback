from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from textual.message import Message


@dataclass
class ProgressBarUpdate(Message):
    total: int
    progress: int


@dataclass
class ProgressBarAdvance(Message):
    amount: int


@dataclass
class TableUpdate(Message):
    update_from: str


@dataclass
class FileChanged(Message):
    path: Path
    change_type: str = "modified"
    old_path: Optional[Path] = None


class BarbackLoaded(Message):
    pass
