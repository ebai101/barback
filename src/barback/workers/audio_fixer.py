import asyncio
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import cpu_count
from pathlib import Path

from textual import work

from barback.audio_processor import AudioProcessor
from barback.state import BarbackState
from barback.util.messages import ProgressBarAdvance, ProgressBarUpdate
from barback.util.protocol import BarbackProtocol


def fix_sr_bd_single_file(
    processor: AudioProcessor, filepath: Path
) -> tuple[Path, bool, str]:
    """
    Fix a single file's sample rate and bit depth.
    Returns (filepath, success, error_message)
    """
    try:
        processor.fix_sr_bd(filepath)
        return (filepath, True, "")
    except Exception as e:
        return (filepath, False, str(e))


@work
async def fix_sr_bd_selected_file(
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
            executor, fix_sr_bd_single_file, processor, filepath
        )

        if success:
            app.info(f"Fixed {filepath.name} (file watcher will update table)")
        else:
            app.info(f"Error fixing {filepath.name}: {error}")

    finally:
        executor.shutdown(wait=True)


@work
async def fix_sr_bd_all_files(
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
                executor, fix_sr_bd_single_file, processor, filepath
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


def fix_microfades_single_file(
    processor: AudioProcessor,
    filepath: Path,
    fadein_samples: int = 35,
    fadeout_samples: int = 90,
) -> tuple[Path, bool, str]:
    """
    Apply microfades to a single file.
    Returns (filepath, success, error_message).
    """
    try:
        processor.apply_microfades(filepath, fadein_samples, fadeout_samples)
        return (filepath, True, "")
    except Exception as e:
        return (filepath, False, str(e))


@work
async def fix_microfades_selected_file(
    app: BarbackProtocol,
    state: BarbackState,
    processor: AudioProcessor,
    filepath: Path,
) -> None:
    """Async worker to apply microfades to a single selected file."""
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        app.info(f"Applying microfades to {filepath.name}...")
        loop = asyncio.get_event_loop()
        result_path, success, error = await loop.run_in_executor(
            executor,
            fix_microfades_single_file,
            processor,
            filepath,
        )

        if success:
            app.info(f"Applied microfades to {filepath.name}")
        else:
            app.info(f"Error applying microfades to {filepath.name}: {error}")
    finally:
        executor.shutdown(wait=True)


@work
async def fix_microfades_all_files(
    app: BarbackProtocol,
    state: BarbackState,
    processor: AudioProcessor,
    filepaths: list[Path],
) -> None:
    """Async worker to apply microfades to multiple files with progress tracking."""
    executor = ThreadPoolExecutor(max_workers=cpu_count())
    try:
        total = len(filepaths)
        app.post_message(ProgressBarUpdate(total, 0))
        app.info(f"Applying microfades to {total} files...")

        async def fix_one(filepath: Path) -> tuple[Path, bool, str]:
            """Async wrapper for fixing one file."""
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                executor,
                fix_microfades_single_file,
                processor,
                filepath,
            )
            app.post_message(ProgressBarAdvance(1))
            return result

        tasks = [fix_one(f) for f in filepaths]
        results = await asyncio.gather(*tasks)

        success_count = sum(1 for (_, success, _) in results if success)
        failure_count = total - success_count

        if failure_count > 0:
            app.info(
                f"Applied microfades to {success_count}/{total} files ({failure_count} failed)"
            )
        else:
            app.info(f"Applied microfades to {total} files successfully")
    finally:
        executor.shutdown(wait=True)


def fix_all_issues_single_file(
    processor: AudioProcessor,
    filepath: Path,
) -> tuple[Path, bool, str]:
    """
    Apply all possible fixes to a single file (SRBD + microfades).
    Returns (filepath, success, error_message).
    """
    try:
        processor.fix_sr_bd(filepath)
        processor.apply_microfades(filepath)
        return (filepath, True, "")
    except Exception as e:
        return (filepath, False, str(e))


@work
async def fix_all_issues_files(
    app: BarbackProtocol,
    state: BarbackState,
    processor: AudioProcessor,
    filepaths: list[Path],
) -> None:
    """Async worker to apply all fixes to multiple files."""
    executor = ThreadPoolExecutor(max_workers=cpu_count())
    try:
        total = len(filepaths)
        app.post_message(ProgressBarUpdate(total, 0))
        app.info(f"Applying all fixes to {total} files...")

        async def fix_one(filepath: Path) -> tuple[Path, bool, str]:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                executor,
                fix_all_issues_single_file,
                processor,
                filepath,
            )
            app.post_message(ProgressBarAdvance(1))
            return result

        tasks = [fix_one(f) for f in filepaths]
        results = await asyncio.gather(*tasks)

        success_count = sum(1 for (_, success, _) in results if success)
        failure_count = total - success_count

        if failure_count > 0:
            app.info(
                f"Applied all fixes to {success_count}/{total} files ({failure_count} failed)"
            )
        else:
            app.info(f"Applied all fixes to {total} files successfully")
    finally:
        executor.shutdown(wait=True)
