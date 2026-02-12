from dataclasses import dataclass
from pathlib import Path
from typing import Literal

IssueKind = Literal["SR/BD", "Silence", "ZC", "Loop", "Key sig"]


@dataclass
class Issue:
    kind: IssueKind
    message: str


@dataclass
class LoopResponse:
    file_path: Path
    is_loop: bool
    response: str
    bpm: int | None = None
    num_bars: int | None = None
    bar_len_samples: float | None = None
    expected_samples: float | None = None
    target_samples: int | None = None
    sample_diff: float | None = None
