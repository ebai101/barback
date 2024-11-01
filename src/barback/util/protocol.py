from typing import Protocol, runtime_checkable

from textual.message import Message


@runtime_checkable
class BarbackProtocol(Protocol):
    def info(self, message: str) -> None: ...
    def post_message(self, message: Message) -> bool: ...
