from dataclasses import dataclass
from pathlib import Path
from typing import Literal

IssueType = Literal["SR/BD", "Silence", "ZC", "Loop", "Key sig"]


@dataclass
class Issue:
    kind: IssueType
    message: str


@dataclass
class LoopResponse:
    filename: Path
    is_loop: bool
    response: str
    bpm: int | None = None
    num_bars: int | None = None
