from collections.abc import Iterable
from pathlib import Path

from textual.binding import Binding
from textual.widgets import DirectoryTree


class DirTree(DirectoryTree):
    """Directory tree that only shows folders."""

    BINDINGS = (
        Binding("j", "cursor_down", "Cursor down", show=False),
        Binding("k", "cursor_up", "Cursor up", show=False),
    )

    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        return sorted(
            (path for path in paths if path.is_dir()), key=lambda p: p.name.lower()
        )
