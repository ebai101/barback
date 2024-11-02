import asyncio
from concurrent.futures import ProcessPoolExecutor
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


def get_valid_audio_files(dirname: Path) -> list[Path]:
    valid_extensions = (".mp3", ".flac", ".wav", ".aif", ".aiff")
    if dirname.is_dir():
        files = [
            file.resolve()
            for file in dirname.rglob("*")
            if file.is_file() and file.suffix.lower() in valid_extensions
        ]
        if not files:
            return []
        return files
    else:
        return []


@work
async def init_audio_data(app: BarbackProtocol, state: BarbackState) -> None:
    state.executor = ProcessPoolExecutor(max_workers=cpu_count())

    audio_files = get_valid_audio_files(state.audio_dir)
    app.post_message(ProgressBarUpdate(len(audio_files), 0))

    async def _proc(file: Path) -> AudioFile:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(state.executor, AudioFile, file)
        app.post_message(ProgressBarAdvance(1))
        return result

    app.info("Barback is starting...")
    tasks = [_proc(file) for file in audio_files]
    results = await asyncio.gather(*tasks)
    # results = [await _proc(file) for file in audio_files]

    for af in results:
        state.audio_data.add_row(
            AudioDataRow(
                file=af,
                duration=af.duration,
                sample_rate=af.sample_rate,
                bit_depth=af.bit_depth,
            )
        )

    app.info(f"Barback has started, indexing {len(audio_files)} files")
    app.post_message(BarbackLoaded())
    app.post_message(TableUpdate("init_audio_data"))
    state.executor.shutdown()
