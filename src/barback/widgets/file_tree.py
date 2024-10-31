from pathlib import Path
from typing import Iterable

from textual.binding import Binding
from textual.widgets import DirectoryTree


class FileTree(DirectoryTree):
    BINDINGS = [
        Binding("j", "cursor_down", "Cursor down", show=False),
        Binding("k", "cursor_up", "Cursor up", show=False),
    ]

    def __init__(self, path: str | Path, id: str = ""):
        self.selected_dir = path
        super().__init__(path, id=id)

    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        return [path for path in paths if path.is_dir()]
