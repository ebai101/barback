from pathlib import Path

from textual import work
from watchfiles import awatch

from barback.state import BarbackState
from barback.util.messages import FileChanged
from barback.util.protocol import BarbackProtocol


def is_temp_file(filename: str) -> bool:
    temp_patterns = ["RX Temp Save File", ".tmp"]
    return any(pattern in filename for pattern in temp_patterns)


@work
async def delete_file(app: BarbackProtocol, state: BarbackState) -> None:
    return


@work
async def watch_files(app: BarbackProtocol, state: BarbackState) -> None:
    watch_path = state.audio_dir

    async for changes in awatch(watch_path):
        for change_type, path_str in changes:
            path = Path(path_str)
            filename = path.name
            if is_temp_file(filename):
                continue
            if change_type == 1:  # created
                app.post_message(FileChanged(path, "created"))
            elif change_type == 2:  # modified
                app.post_message(FileChanged(path, "modified"))
            elif change_type == 3:  # deleted
                app.post_message(FileChanged(path, "deleted"))
