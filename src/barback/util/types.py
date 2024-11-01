from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

FinalizerIssueKind = Literal["SR/BD", "Silence", "ZC", "Loop", "Key sig"]


@dataclass
class FinalizerIssue:
    kind: FinalizerIssueKind
    message: str


@dataclass
class LoopResponse:
    filename: Path
    is_loop: bool
    response: str
    bpm: Optional[int] = None
    num_bars: Optional[int] = None
