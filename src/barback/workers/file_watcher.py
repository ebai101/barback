import asyncio
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import cpu_count
from pathlib import Path

from textual import work
from watchfiles import Change, awatch

from barback.audio_file import AudioFileError
from barback.state import BarbackState
from barback.util.logger import get_logger
from barback.util.messages import TableUpdate
from barback.util.protocol import BarbackProtocol
from barback.workers.file_processor import process_file_with_validation


def is_temp_file(filename: str) -> bool:
    """Filter out temporary files created by editors/DAWs."""
    temp_patterns = ["RX Temp Save File", ".tmp", "~"]
    return any(pattern in filename for pattern in temp_patterns)


def is_valid_wav(path: Path) -> bool:
    """Check if path is a .wav file we care about."""
    return path.suffix.lower() == ".wav" and not is_temp_file(path.name)


@work
async def watch_files(app: BarbackProtocol, state: BarbackState) -> None:
    """
    Watch the audio directory for changes and reprocess affected files.

    - Created/Modified: revalidate the file and update the table
    - Deleted: remove from the table
    """
    watch_path = state.audio_dir
    executor = ThreadPoolExecutor(max_workers=cpu_count())

    app.info(f"Watching {watch_path} for changes...")

    try:
        async for changes in awatch(watch_path):
            for change_type, path_str in changes:
                path = Path(path_str)

                # Skip non-wav and temp files
                if not is_valid_wav(path):
                    continue

                # Handle different change types
                if change_type == Change.added:
                    await _handle_file_added(app, state, executor, path)

                elif change_type == Change.deleted:
                    await _handle_file_deleted(app, state, path)

    finally:
        executor.shutdown(wait=True)


async def _handle_file_added(
    app: BarbackProtocol,
    state: BarbackState,
    executor: ThreadPoolExecutor,
    path: Path,
) -> None:
    """Process a newly created file."""
    logger = get_logger()
    loop = asyncio.get_event_loop()

    try:
        row = await loop.run_in_executor(
            executor,
            process_file_with_validation,
            path,
        )

        if row is None:
            raise AudioFileError("failed to process audio file")

        state.audio_data.add_row(row)
        app.post_message(TableUpdate("file_added"))

        if row.issues:
            issue_count = len(row.issues)
            logger.debug(
                f"File watcher: Added file ({issue_count} issues) - {path.name}",
                extra={"filepath": path},
            )
        else:
            logger.debug(
                f"File watcher: Added file (no issues) - {path.name}",
                extra={"filepath": path},
            )

    except Exception:
        logger.debug(
            f"File watcher: Failed to add file - {path.name}",
            extra={"filepath": path},
            exc_info=True,
        )


async def _handle_file_deleted(
    app: BarbackProtocol,
    state: BarbackState,
    path: Path,
) -> None:
    """Remove a deleted file from the table."""
    logger = get_logger()

    if path in state.audio_data:
        state.audio_data.delete_row(path)
        app.post_message(TableUpdate("file_deleted"))
        logger.debug(
            f"File watcher: File deleted - {path.name}", extra={"filepath": path}
        )
    else:
        logger.debug(
            f"File watcher: File deleted but not in table - {path.name}",
            extra={"filepath": path},
        )
