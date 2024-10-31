import asyncio
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import cpu_count
from pathlib import Path

import pandas as pd
from textual import work

from barback.audio_file import AudioFile
from barback.messages import ProgressBarAdvance, ProgressBarUpdate, TableUpdate
from barback.state import BarbackState
from barback.util import BarbackProtocol, get_valid_audio_files


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

    new_data = pd.DataFrame(results, columns=["File"])
    new_data["Duration"] = new_data["File"].apply(lambda x: x.duration)
    new_data["Sample rate"] = new_data["File"].apply(lambda x: x.sample_rate)
    new_data["Bit depth"] = new_data["File"].apply(lambda x: x.bit_depth)
    state.audio_data = (
        pd.concat([state.audio_data, new_data], ignore_index=True)
        .infer_objects()
        .fillna("")
    )

    app.info(f"Barback has started, indexing {len(audio_files)} files")
    app.post_message(TableUpdate("init_audio_data"))
    state.loaded = True
    state.executor.shutdown()
