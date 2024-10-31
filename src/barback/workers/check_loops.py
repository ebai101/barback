import asyncio
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import cpu_count
from typing import Tuple

import pandas as pd
from textual import work

from barback.audio_file import AudioFile, IsLoopResponse
from barback.messages import ProgressBarAdvance, ProgressBarUpdate, TableUpdate
from barback.state import BarbackState
from barback.util import BarbackProtocol


def check_loops_proc(af: AudioFile) -> Tuple[IsLoopResponse, str]:
    af.load(mono=True)
    is_loop = af.is_loop()
    zc = af.get_start_end_zero_crossing()
    af.unload()

    return is_loop, zc


@work
async def check_loops(app: BarbackProtocol, state: BarbackState) -> None:
    state.executor = ProcessPoolExecutor(max_workers=cpu_count())

    files = state.audio_data["File"].tolist()
    total_tasks = len(files)

    app.info("Checking loops")
    app.post_message(ProgressBarUpdate(total_tasks, 0))

    async def _proc(file: AudioFile) -> Tuple[IsLoopResponse, str]:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(state.executor, check_loops_proc, file)
        app.post_message(ProgressBarAdvance(1))
        return result

    tasks = [_proc(file) for file in files]
    results = await asyncio.gather(*tasks)
    results_dict = {
        r[0].filename: {
            "Loop": r[0].response,
            "BPM": r[0].bpm,
            "Bars": r[0].num_bars,
            "ZC": r[1],
        }
        for r in results
    }

    new_cols = ["Loop", "BPM", "Bars", "ZC"]
    state.audio_data[new_cols] = state.audio_data["File"].apply(
        lambda x: pd.Series(results_dict.get(x.filename, [None] * 4))
    )
    app.post_message(TableUpdate("check_loops"))
    app.info("Done checking loops")
    state.executor.shutdown()
