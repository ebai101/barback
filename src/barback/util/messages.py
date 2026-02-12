from dataclasses import dataclass

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


class BarbackLoaded(Message):
    pass
