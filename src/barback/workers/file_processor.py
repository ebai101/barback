import asyncio
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import cpu_count
from pathlib import Path

from textual import work

from barback.audio_data import AudioDataRow
from barback.audio_file import AudioFile
from barback.state import BarbackState
from barback.util.logger import get_logger
from barback.util.messages import (
    BarbackLoaded,
    ProgressBarAdvance,
    ProgressBarUpdate,
    TableUpdate,
)
from barback.util.protocol import BarbackProtocol
from barback.util.types import Issue
from barback.validation import validate_audio_file


def get_valid_audio_files(dirname: Path) -> list[Path]:
    """Discover all .wav files recursively under dirname."""
    logger = get_logger()
    if not dirname.is_dir():
        logger.warning(f"Attempted to scan non-directory: {dirname}")
        return []

    files = [file.resolve() for file in dirname.rglob("*.wav") if file.is_file()]
    logger.info(f"Discovered {len(files)} .wav files in {dirname}")
    return files


def process_file_with_validation(filepath: Path) -> AudioDataRow:
    """
    Load, validate, and build an AudioDataRow for a single file.
    Returns None if file cannot be processed.
    """
    logger = get_logger()
    try:
        logger.debug(f"Processing file: {filepath.name}", extra={"filepath": filepath})

        af = AudioFile(filepath)
        af.load(mono=True)
        issues = validate_audio_file(af)
        loop_resp = af.is_loop()
        loop_str = "Yes" if loop_resp.is_loop else "No"
        zc_status = af.get_start_end_zero_crossing()
        af.unload()

        if issues:
            logger.debug(
                f"Validated {filepath.name}: {len(issues)} issue(s) - {', '.join(i.kind for i in issues)}",
                extra={"filepath": filepath, "issues": len(issues)},
            )
        else:
            logger.debug(
                f"Validated {filepath.name}: No issues", extra={"filepath": filepath}
            )

        return AudioDataRow(
            file=af,
            duration=af.duration,
            sample_rate=af.sample_rate,
            bit_depth=af.subtype,
            loop=loop_str,
            bpm=loop_resp.bpm,
            bars=loop_resp.num_bars,
            zc=zc_status if zc_status else "OK",
            issues=issues,
        )
    except Exception as e:
        logger.exception(
            f"Failed to process file: {filepath.name}",
            extra={"filepath": filepath},
        )
        af = AudioFile(filepath)
        return AudioDataRow(
            file=af,
            issues=[Issue("SR/BD", f"Error: {e!s}")],
        )


@work
async def init_audio_data(app: BarbackProtocol, state: BarbackState) -> None:
    """
    Initial scan: discover all .wav files, validate them, and populate AudioData.
    """
    logger = get_logger()
    executor = ThreadPoolExecutor(max_workers=cpu_count())

    try:
        logger.info(f"Starting initial audio directory scan: {state.audio_dir}")
        audio_files = get_valid_audio_files(state.audio_dir)

        if not audio_files:
            logger.warning(f"No .wav files found in {state.audio_dir}")
            app.info("No .wav files found in directory")
            app.post_message(BarbackLoaded())
            return

        app.post_message(ProgressBarUpdate(len(audio_files), 0))
        app.info(f"Scanning {len(audio_files)} files...")

        async def _process_one(filepath: Path) -> AudioDataRow | None:
            """Async wrapper for process_file_with_validation."""
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                executor, process_file_with_validation, filepath
            )
            app.post_message(ProgressBarAdvance(1))
            return result

        tasks = [_process_one(f) for f in audio_files]
        rows = await asyncio.gather(*tasks)

        for row in rows:
            state.audio_data.add_row(row)

        files_with_issues = sum(1 for row in rows if row and row.issues)
        logger.info(
            f"Initial scan complete: {len(audio_files)} files indexed, {files_with_issues} with issues",
            extra={
                "total_files": len(audio_files),
                "files_with_issues": files_with_issues,
            },
        )

        app.info(f"Indexed {len(audio_files)} files ({files_with_issues} with issues)")
        app.post_message(BarbackLoaded())
        app.post_message(TableUpdate("init_audio_data"))

    finally:
        executor.shutdown(wait=True)
