from collections.abc import Iterable
from pathlib import Path

from textual.widgets import DirectoryTree


class DirTree(DirectoryTree):
    """Directory tree that only shows folders."""

    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        return sorted(
            (path for path in paths if path.is_dir()), key=lambda p: p.name.lower()
        )
