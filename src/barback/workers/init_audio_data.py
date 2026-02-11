import asyncio
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import cpu_count
from pathlib import Path

from textual import work

from barback.audio_data import AudioDataRow
from barback.audio_file import AudioFile
from barback.state import BarbackState
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
    if not dirname.is_dir():
        return []

    # Restrict to .wav only for your 44.1/24-bit requirement
    files = [file.resolve() for file in dirname.rglob("*.wav") if file.is_file()]
    return files


def process_file_with_validation(filepath: Path) -> AudioDataRow | None:
    """
    Load, validate, and build an AudioDataRow for a single file.
    Returns None if file cannot be processed.
    """
    try:
        af = AudioFile(filepath)
        af.load(mono=True)
        issues = validate_audio_file(af)
        loop_resp = af.is_loop()
        loop_str = "Yes" if loop_resp.is_loop else "No"
        sil_start, sil_end = af.get_start_end_silence()
        zc_status = af.get_start_end_zero_crossing()
        af.unload()

        return AudioDataRow(
            file=af,
            duration=af.duration,
            sample_rate=af.sample_rate,
            bit_depth=af.bit_depth,
            loop=loop_str,
            bpm=loop_resp.bpm,
            bars=loop_resp.num_bars,
            zc=zc_status if zc_status else "OK",
            issues=issues,
        )
    except Exception as e:
        # Return a row with error info
        af = AudioFile(filepath)
        return AudioDataRow(
            file=af,
            issues=[Issue("SR/BD", f"Error: {str(e)}")],
        )


@work
async def init_audio_data(app: BarbackProtocol, state: BarbackState) -> None:
    """
    Initial scan: discover all .wav files, validate them, and populate AudioData.
    """
    # Create a local executor (not stored in state)
    executor = ThreadPoolExecutor(max_workers=cpu_count())

    try:
        audio_files = get_valid_audio_files(state.audio_dir)

        if not audio_files:
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

        # Process all files in parallel
        tasks = [_process_one(f) for f in audio_files]
        rows = await asyncio.gather(*tasks)

        # Populate the in-memory table
        for row in rows:
            state.audio_data.add_row(row)

        # Count files with issues for user feedback
        files_with_issues = sum(1 for row in rows if row.issues)

        app.info(f"Indexed {len(audio_files)} files ({files_with_issues} with issues)")
        app.post_message(BarbackLoaded())
        app.post_message(TableUpdate("init_audio_data"))

    finally:
        executor.shutdown(wait=True)
