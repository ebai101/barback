import asyncio
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import cpu_count
from pathlib import Path

from textual import work

from barback.audio_processor import AudioProcessor
from barback.state import BarbackState
from barback.util.messages import ProgressBarAdvance, ProgressBarUpdate
from barback.util.protocol import BarbackProtocol


def fix_single_file(
    processor: AudioProcessor, filepath: Path
) -> tuple[Path, bool, str]:
    """
    Fix a single file's sample rate and bit depth.
    Returns (filepath, success, error_message)
    """
    try:
        processor.fix_samplerate_and_bitdepth(filepath)
        return (filepath, True, "")
    except Exception as e:
        return (filepath, False, str(e))


@work
async def fix_selected_file(
    app: BarbackProtocol, state: BarbackState, processor: AudioProcessor, filepath: Path
) -> None:
    """
    Async worker to fix a single selected file.
    """
    executor = ThreadPoolExecutor(max_workers=1)

    try:
        app.info(f"Fixing {filepath.name}...")

        loop = asyncio.get_event_loop()
        result_path, success, error = await loop.run_in_executor(
            executor, fix_single_file, processor, filepath
        )

        if success:
            app.info(f"Fixed {filepath.name} (file watcher will update table)")
        else:
            app.info(f"Error fixing {filepath.name}: {error}")

    finally:
        executor.shutdown(wait=True)


@work
async def fix_all_files(
    app: BarbackProtocol,
    state: BarbackState,
    processor: AudioProcessor,
    filepaths: list[Path],
) -> None:
    """
    Async worker to fix multiple files with progress tracking.
    """
    executor = ThreadPoolExecutor(max_workers=cpu_count())

    try:
        total = len(filepaths)
        app.post_message(ProgressBarUpdate(total, 0))
        app.info(f"Fixing {total} files...")

        async def _fix_one(filepath: Path) -> tuple[Path, bool, str]:
            """Async wrapper for fixing one file."""
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                executor, fix_single_file, processor, filepath
            )
            app.post_message(ProgressBarAdvance(1))
            return result

        # Process all files in parallel
        tasks = [_fix_one(f) for f in filepaths]
        results = await asyncio.gather(*tasks)

        # Count successes and failures
        success_count = sum(1 for _, success, _ in results if success)
        failure_count = total - success_count

        if failure_count > 0:
            app.info(f"Fixed {success_count}/{total} files ({failure_count} failed)")
        else:
            app.info(f"Fixed {total} files successfully")

    finally:
        executor.shutdown(wait=True)
