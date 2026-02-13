import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import cpu_count

from textual import work

from barback.audio_file import AudioFile
from barback.audio_processor import AudioProcessor
from barback.state import BarbackState
from barback.util.logger import get_logger
from barback.util.messages import ProgressBarAdvance, ProgressBarUpdate
from barback.util.protocol import BarbackProtocol

# =============================================================================
# SR/BD Fix Functions
# =============================================================================


def _fix_srbd_single_file(
    processor: AudioProcessor, af: AudioFile
) -> tuple[AudioFile, bool, str]:
    """
    Fix a single file's sample rate and bit depth.
    Returns (filepath, success, error_message).
    """
    logger = get_logger()
    start_time = time.time()

    logger.info(
        f"Starting SR/BD fix for: {af.file_path.name}",
        extra={"filepath": af, "operation": "fix_srbd"},
    )
    try:
        processor.fix_srbd(af)
        duration = (time.time() - start_time) * 1000
        logger.info(
            f"Successfully fixed SR/BD for: {af.file_path.name} in {duration:.2f}ms",
            extra={"filepath": af, "operation": "fix_srbd", "duration": duration},
        )
        return (af, True, "")
    except Exception as e:
        duration = (time.time() - start_time) * 1000
        logger.error(
            f"Failed to fix SR/BD for: {af.file_path.name} after {duration:.2f}ms",
            extra={"filepath": af, "operation": "fix_srbd", "duration": duration},
            exc_info=True,
        )
        return (af, False, str(e))


@work
async def fix_srbd_selected_file(
    app: BarbackProtocol,
    state: BarbackState,
    processor: AudioProcessor,
    af: AudioFile,
) -> None:
    """Async worker to fix SR/BD for a single selected file."""
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        app.info(f"Fixing SR/BD for {af.file_path.name}...")
        loop = asyncio.get_event_loop()
        result_af, success, error = await loop.run_in_executor(
            executor,
            _fix_srbd_single_file,
            processor,
            af,
        )

        if success:
            app.info(f"Fixed SR/BD: {result_af.file_path.name}")
        else:
            app.info(f"Error fixing SR/BD for {result_af.file_path.name}: {error}")
    finally:
        executor.shutdown(wait=True)


@work
async def fix_srbd_all_files(
    app: BarbackProtocol,
    state: BarbackState,
    processor: AudioProcessor,
    afiles: list[AudioFile],
) -> None:
    """Async worker to fix SR/BD for multiple files with progress tracking."""
    executor = ThreadPoolExecutor(max_workers=cpu_count())
    try:
        total = len(afiles)
        app.post_message(ProgressBarUpdate(total, 0))
        app.info(f"Fixing SR/BD for {total} files...")

        async def fix_one(af: AudioFile) -> tuple[AudioFile, bool, str]:
            """Async wrapper for fixing one file."""
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                executor,
                _fix_srbd_single_file,
                processor,
                af,
            )
            app.post_message(ProgressBarAdvance(1))
            return result

        tasks = [fix_one(f) for f in afiles]
        results = await asyncio.gather(*tasks)

        success_count = sum(1 for (_, success, _) in results if success)
        failure_count = total - success_count

        if failure_count > 0:
            app.info(
                f"Fixed SR/BD for {success_count}/{total} files ({failure_count} failed)"
            )
        else:
            app.info(f"Fixed SR/BD for {total} files successfully")
    finally:
        executor.shutdown(wait=True)


# =============================================================================
# ZC Fix Functions
# =============================================================================


def _fix_zc_single_file(
    processor: AudioProcessor,
    af: AudioFile,
    fadein_samples: int = 35,
    fadeout_samples: int = 90,
) -> tuple[AudioFile, bool, str]:
    """
    Apply microfades to a single file.
    Returns (filepath, success, error_message).
    """
    logger = get_logger()
    start_time = time.time()

    logger.info(
        f"Starting ZC fix for: {af.file_path.name}",
        extra={"filepath": af, "operation": "fix_zc"},
    )
    try:
        processor.apply_microfades(af, fadein_samples, fadeout_samples)
        duration = (time.time() - start_time) * 1000
        logger.info(
            f"Successfully fixed ZC for: {af.file_path.name} in {duration:.2f}ms",
            extra={"filepath": af, "operation": "fix_zc", "duration": duration},
        )
        return (af, True, "")
    except Exception as e:
        duration = (time.time() - start_time) * 1000
        logger.error(
            f"Failed to fix ZC for: {af.file_path.name} after {duration:.2f}ms",
            extra={"filepath": af, "operation": "fix_zc", "duration": duration},
            exc_info=True,
        )
        return (af, False, str(e))


@work
async def fix_zc_selected_file(
    app: BarbackProtocol,
    state: BarbackState,
    processor: AudioProcessor,
    af: AudioFile,
) -> None:
    """Async worker to apply microfades to a single selected file."""
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        app.info(f"Applying microfades to {af.file_path.name}...")
        loop = asyncio.get_event_loop()
        result_af, success, error = await loop.run_in_executor(
            executor,
            _fix_zc_single_file,
            processor,
            af,
        )

        if success:
            app.info(f"Applied microfades: {result_af.file_path.name}")
        else:
            app.info(
                f"Error applying microfades to {result_af.file_path.name}: {error}"
            )
    finally:
        executor.shutdown(wait=True)


@work
async def fix_zc_all_files(
    app: BarbackProtocol,
    state: BarbackState,
    processor: AudioProcessor,
    afiles: list[AudioFile],
) -> None:
    """Async worker to apply microfades to multiple files with progress tracking."""
    executor = ThreadPoolExecutor(max_workers=cpu_count())
    try:
        total = len(afiles)
        app.post_message(ProgressBarUpdate(total, 0))
        app.info(f"Applying microfades to {total} files...")

        async def fix_one(af: AudioFile) -> tuple[AudioFile, bool, str]:
            """Async wrapper for fixing one file."""
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                executor,
                _fix_zc_single_file,
                processor,
                af,
            )
            app.post_message(ProgressBarAdvance(1))
            return result

        tasks = [fix_one(f) for f in afiles]
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
# Loop Fix Functions
# =============================================================================


def _fix_loop_single_file(
    processor: AudioProcessor,
    af: AudioFile,
    fadeout_samples: int = 90,
) -> tuple[AudioFile, bool, str]:
    """
    Fix a single file's loop length (trim/pad + fade out).
    Returns (af, success, note_or_error).

    success=False only on exception.
    If success=True and note_or_error != "", it was intentionally skipped.
    """
    logger = get_logger()
    start_time = time.time()

    logger.info(
        f"Starting Loop fix for: {af.file_path.name}",
        extra={"filepath": af, "operation": "fix_loop"},
    )
    try:
        note = processor.fix_loop(af, fadeout_samples=fadeout_samples)
        duration = (time.time() - start_time) * 1000

        if note:
            logger.info(
                note,
                extra={"filepath": af, "operation": "fix_loop", "duration": duration},
            )
        else:
            logger.info(
                f"Successfully fixed Loop for: {af.file_path.name} in {duration:.2f}ms",
                extra={"filepath": af, "operation": "fix_loop", "duration": duration},
            )

        return (af, True, note)

    except Exception as e:
        duration = (time.time() - start_time) * 1000
        logger.error(
            f"Failed to fix Loop for: {af.file_path.name} after {duration:.2f}ms",
            extra={"filepath": af, "operation": "fix_loop", "duration": duration},
            exc_info=True,
        )
        return (af, False, str(e))


@work
async def fix_loop_selected_file(
    app: BarbackProtocol,
    state: BarbackState,
    processor: AudioProcessor,
    af: AudioFile,
) -> None:
    """Async worker to fix Loop for a single selected file."""
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        app.info(f"Fixing Loop for {af.file_path.name}...")
        loop = asyncio.get_event_loop()
        result_af, success, note = await loop.run_in_executor(
            executor,
            _fix_loop_single_file,
            processor,
            af,
        )

        if success:
            if note:
                app.info(note)
            else:
                app.info(f"Fixed Loop: {result_af.file_path.name}")
        else:
            app.info(f"Error fixing Loop for {result_af.file_path.name}: {note}")
    finally:
        executor.shutdown(wait=True)


@work
async def fix_loop_all_files(
    app: BarbackProtocol,
    state: BarbackState,
    processor: AudioProcessor,
    afiles: list[AudioFile],
) -> None:
    """Async worker to fix Loop for multiple files with progress tracking."""
    executor = ThreadPoolExecutor(max_workers=cpu_count())
    try:
        total = len(afiles)
        app.post_message(ProgressBarUpdate(total, 0))
        app.info(f"Fixing Loop for {total} files...")

        async def fix_one(af: AudioFile) -> tuple[AudioFile, bool, str]:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                executor,
                _fix_loop_single_file,
                processor,
                af,
            )
            app.post_message(ProgressBarAdvance(1))
            return result

        tasks = [fix_one(f) for f in afiles]
        results = await asyncio.gather(*tasks)

        failed = sum(1 for (_, success, _) in results if not success)
        skipped = sum(1 for (_, success, note) in results if success and note)
        fixed = total - failed - skipped

        if failed > 0:
            app.info(
                f"Loop fix: {fixed}/{total} fixed ({skipped} skipped, {failed} failed)"
            )
        else:
            app.info(f"Loop fix: {fixed}/{total} fixed ({skipped} skipped)")

    finally:
        executor.shutdown(wait=True)


# =============================================================================
# Combined Fix Functions (SR/BD + Microfades)
# =============================================================================


def _fix_all_issues_single_file(
    processor: AudioProcessor,
    af: AudioFile,
) -> tuple[AudioFile, bool, str]:
    try:
        processor.fix_srbd(af)
        processor.apply_microfades(af)
        processor.fix_loop(af)
        return (af, True, "")
    except Exception as e:
        return (af, False, str(e))


@work
async def fix_all_issues_selected_file(
    app: BarbackProtocol,
    state: BarbackState,
    processor: AudioProcessor,
    af: AudioFile,
) -> None:
    """Async worker to apply all fixes to a single selected file."""
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        app.info(f"Applying all fixes to {af.file_path.name}...")
        loop = asyncio.get_event_loop()
        result_af, success, error = await loop.run_in_executor(
            executor,
            _fix_all_issues_single_file,
            processor,
            af,
        )

        if success:
            app.info(f"Applied all fixes: {result_af.file_path.name}")
        else:
            app.info(f"Error applying fixes to {result_af.file_path.name}: {error}")
    finally:
        executor.shutdown(wait=True)


@work
async def fix_all_issues_all_files(
    app: BarbackProtocol,
    state: BarbackState,
    processor: AudioProcessor,
    afiles: list[AudioFile],
) -> None:
    """Async worker to apply all fixes to multiple files with progress tracking."""
    executor = ThreadPoolExecutor(max_workers=cpu_count())
    try:
        total = len(afiles)
        app.post_message(ProgressBarUpdate(total, 0))
        app.info(f"Applying all fixes to {total} files...")

        async def fix_one(af: AudioFile) -> tuple[AudioFile, bool, str]:
            """Async wrapper for fixing one file."""
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                executor,
                _fix_all_issues_single_file,
                processor,
                af,
            )
            app.post_message(ProgressBarAdvance(1))
            return result

        tasks = [fix_one(f) for f in afiles]
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
