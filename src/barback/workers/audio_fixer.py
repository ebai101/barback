import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import cpu_count
from pathlib import Path

from textual import work

from barback.audio_processor import AudioProcessor
from barback.state import BarbackState
from barback.util.logger import get_logger
from barback.util.messages import ProgressBarAdvance, ProgressBarUpdate
from barback.util.protocol import BarbackProtocol

# =============================================================================
# SRBD Fix Functions
# =============================================================================


def _fix_srbd_single_file(
    processor: AudioProcessor, filepath: Path
) -> tuple[Path, bool, str]:
    """
    Fix a single file's sample rate and bit depth.
    Returns (filepath, success, error_message).
    """
    logger = get_logger()
    start_time = time.time()

    logger.info(
        f"Starting SRBD fix for: {filepath.name}",
        extra={"filepath": filepath, "operation": "fix_srbd"},
    )
    try:
        processor.fix_srbd(filepath)
        duration = (time.time() - start_time) * 1000
        logger.info(
            f"Successfully fixed SRBD for: {filepath.name} in {duration:.2f}ms",
            extra={"filepath": filepath, "operation": "fix_srbd", "duration": duration},
        )
        return (filepath, True, "")
    except Exception as e:
        duration = (time.time() - start_time) * 1000
        logger.error(
            f"Failed to fix SRBD for: {filepath.name} after {duration:.2f}ms",
            extra={"filepath": filepath, "operation": "fix_srbd", "duration": duration},
            exc_info=True,
        )
        return (filepath, False, str(e))


@work
async def fix_srbd_selected_file(
    app: BarbackProtocol,
    state: BarbackState,
    processor: AudioProcessor,
    filepath: Path,
) -> None:
    """Async worker to fix SRBD for a single selected file."""
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        app.info(f"Fixing SRBD for {filepath.name}...")
        loop = asyncio.get_event_loop()
        result_path, success, error = await loop.run_in_executor(
            executor,
            _fix_srbd_single_file,
            processor,
            filepath,
        )

        if success:
            app.info(f"Fixed SRBD: {filepath.name}")
        else:
            app.info(f"Error fixing SRBD for {filepath.name}: {error}")
    finally:
        executor.shutdown(wait=True)


@work
async def fix_srbd_all_files(
    app: BarbackProtocol,
    state: BarbackState,
    processor: AudioProcessor,
    filepaths: list[Path],
) -> None:
    """Async worker to fix SRBD for multiple files with progress tracking."""
    executor = ThreadPoolExecutor(max_workers=cpu_count())
    try:
        total = len(filepaths)
        app.post_message(ProgressBarUpdate(total, 0))
        app.info(f"Fixing SRBD for {total} files...")

        async def fix_one(filepath: Path) -> tuple[Path, bool, str]:
            """Async wrapper for fixing one file."""
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                executor,
                _fix_srbd_single_file,
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
                f"Fixed SRBD for {success_count}/{total} files ({failure_count} failed)"
            )
        else:
            app.info(f"Fixed SRBD for {total} files successfully")
    finally:
        executor.shutdown(wait=True)


# =============================================================================
# ZC Fix Functions
# =============================================================================


def _fix_zc_single_file(
    processor: AudioProcessor,
    filepath: Path,
    fadein_samples: int = 35,
    fadeout_samples: int = 90,
) -> tuple[Path, bool, str]:
    """
    Apply microfades to a single file.
    Returns (filepath, success, error_message).
    """
    logger = get_logger()
    start_time = time.time()

    logger.info(
        f"Starting ZC fix for: {filepath.name}",
        extra={"filepath": filepath, "operation": "fix_zc"},
    )
    try:
        processor.apply_microfades(filepath, fadein_samples, fadeout_samples)
        duration = (time.time() - start_time) * 1000
        logger.info(
            f"Successfully fixed ZC for: {filepath.name} in {duration:.2f}ms",
            extra={"filepath": filepath, "operation": "fix_zc", "duration": duration},
        )
        return (filepath, True, "")
    except Exception as e:
        duration = (time.time() - start_time) * 1000
        logger.error(
            f"Failed to fix ZC for: {filepath.name} after {duration:.2f}ms",
            extra={"filepath": filepath, "operation": "fix_zc", "duration": duration},
            exc_info=True,
        )
        return (filepath, False, str(e))


@work
async def fix_zc_selected_file(
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
            _fix_zc_single_file,
            processor,
            filepath,
        )

        if success:
            app.info(f"Applied microfades: {filepath.name}")
        else:
            app.info(f"Error applying microfades to {filepath.name}: {error}")
    finally:
        executor.shutdown(wait=True)


@work
async def fix_zc_all_files(
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
                _fix_zc_single_file,
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


# =============================================================================
# Combined Fix Functions (SRBD + Microfades)
# =============================================================================


def _fix_all_issues_single_file(
    processor: AudioProcessor,
    filepath: Path,
) -> tuple[Path, bool, str]:
    """
    Apply all possible fixes to a single file (SRBD + microfades).
    Returns (filepath, success, error_message).
    """
    try:
        processor.fix_srbd(filepath)
        processor.apply_microfades(filepath)
        return (filepath, True, "")
    except Exception as e:
        return (filepath, False, str(e))


@work
async def fix_all_issues_selected_file(
    app: BarbackProtocol,
    state: BarbackState,
    processor: AudioProcessor,
    filepath: Path,
) -> None:
    """Async worker to apply all fixes to a single selected file."""
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        app.info(f"Applying all fixes to {filepath.name}...")
        loop = asyncio.get_event_loop()
        result_path, success, error = await loop.run_in_executor(
            executor,
            _fix_all_issues_single_file,
            processor,
            filepath,
        )

        if success:
            app.info(f"Applied all fixes: {filepath.name}")
        else:
            app.info(f"Error applying fixes to {filepath.name}: {error}")
    finally:
        executor.shutdown(wait=True)


@work
async def fix_all_issues_all_files(
    app: BarbackProtocol,
    state: BarbackState,
    processor: AudioProcessor,
    filepaths: list[Path],
) -> None:
    """Async worker to apply all fixes to multiple files with progress tracking."""
    executor = ThreadPoolExecutor(max_workers=cpu_count())
    try:
        total = len(filepaths)
        app.post_message(ProgressBarUpdate(total, 0))
        app.info(f"Applying all fixes to {total} files...")

        async def fix_one(filepath: Path) -> tuple[Path, bool, str]:
            """Async wrapper for fixing one file."""
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                executor,
                _fix_all_issues_single_file,
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
