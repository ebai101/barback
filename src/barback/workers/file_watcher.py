import asyncio
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import cpu_count
from pathlib import Path

from textual import work
from watchfiles import Change, awatch

from barback.audio_file import AudioFileError
from barback.state import BarbackState
from barback.util.messages import TableUpdate
from barback.util.protocol import BarbackProtocol
from barback.workers.init_audio_data import process_file_with_validation


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

                elif change_type == Change.modified:
                    await _handle_file_modified(app, state, executor, path)

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
    app.info(f"New file detected: {path.name}")

    # Process in executor
    loop = asyncio.get_event_loop()
    try:
        row = await loop.run_in_executor(
            executor,
            process_file_with_validation,
            path,
        )

        if row is None:
            raise AudioFileError("failed to process audio file")

        # Add to table
        state.audio_data.add_row(row)
        app.post_message(TableUpdate("file_added"))

        # User feedback
        if row.issues:
            issue_count = len(row.issues)
            app.info(f"Added {path.name} ({issue_count} issues)")
        else:
            app.info(f"Added {path.name} (no issues)")

    except Exception as e:
        app.info(f"Error processing {path.name}: {e}")


async def _handle_file_modified(
    app: BarbackProtocol,
    state: BarbackState,
    executor: ThreadPoolExecutor,
    path: Path,
) -> None:
    """Reprocess a modified file."""
    app.info(f"File modified: {path.name}")

    loop = asyncio.get_event_loop()
    try:
        row = await loop.run_in_executor(
            executor,
            process_file_with_validation,
            path,
        )

        if row is None:
            raise AudioFileError("failed to process audio file")

        # Update existing row or add if somehow missing
        if path in state.audio_data:
            # Remove old, add new (simpler than partial updates)
            old_row = state.audio_data.get_row(path)
            if old_row:
                # Could compare hashes here if you add that field later
                pass

            # Update by replacing
            state.audio_data.update_row(
                path,
                duration=row.duration,
                sample_rate=row.sample_rate,
                bit_depth=row.bit_depth,
                loop=row.loop,
                bpm=row.bpm,
                bars=row.bars,
                zc=row.zc,
                issues=row.issues,
            )
        else:
            # File wasn't in table, add it
            state.audio_data.add_row(row)

        app.post_message(TableUpdate("file_modified"))

        # User feedback
        if row.issues:
            issue_count = len(row.issues)
            app.info(f"Updated {path.name} ({issue_count} issues)")
        else:
            app.info(f"Updated {path.name} (no issues)")

    except Exception as e:
        app.info(f"Error reprocessing {path.name}: {e}")


async def _handle_file_deleted(
    app: BarbackProtocol,
    state: BarbackState,
    path: Path,
) -> None:
    """Remove a deleted file from the table."""
    if path in state.audio_data:
        app.info(f"File deleted: {path.name}")
        state.audio_data.delete_row(path)
        app.post_message(TableUpdate("file_deleted"))
    else:
        app.info(f"File deleted but not in table: {path.name}")
