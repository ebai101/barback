import asyncio
from concurrent.futures import ProcessPoolExecutor
from itertools import combinations
from multiprocessing import cpu_count
from typing import Tuple

import numpy as np
import pandas as pd
from textual import work

from barback.audio_file import AudioFile
from barback.messages import ProgressBarAdvance, ProgressBarUpdate, TableUpdate
from barback.state import BarbackState
from barback.util import BarbackProtocol


def find_duplicates_preproc(af: AudioFile) -> AudioFile:
    af.load(sample_rate=22050, mono=True)
    if len(af.audio) < 1024:
        print(len(af.audio))
        pad_width = 1024 - len(af.audio)
        af.audio = np.pad(af.audio, (0, pad_width), mode="constant")

    af.zero_crossings = af.calc_zero_crossings()
    af.chroma = af.calc_chroma()
    af.spectral_contrast = af.calc_spectral_contrast()
    return af


def find_duplicates_proc(afA: AudioFile, afB: AudioFile) -> Tuple[str, str, float]:
    if abs(afA.duration - afB.duration) > 0.1:
        return afA.filename.name, afB.filename.name, 0.0
    s = afA.weighted_similarity(afB)
    return s  # afA, afB, similarity


@work
async def find_duplicates(app: BarbackProtocol, state: BarbackState) -> None:
    state.executor = ProcessPoolExecutor(max_workers=cpu_count())

    files = state.audio_data["File"].tolist()
    total_tasks = len(files)
    app.post_message(ProgressBarUpdate(total_tasks, 0))

    async def _preproc(file: AudioFile) -> AudioFile:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            state.executor, find_duplicates_preproc, file
        )
        app.post_message(ProgressBarAdvance(1))
        return result

    app.info(f"Preprocessing {total_tasks} files")
    preproc_tasks = [_preproc(file) for file in files]
    preproc_files = await asyncio.gather(*preproc_tasks)

    file_combinations = list(
        (i, j) for ((i, _), (j, _)) in combinations(enumerate(preproc_files), 2)
    )
    total_tasks = len(file_combinations)
    app.post_message(ProgressBarUpdate(total_tasks, 0))

    async def _proc(combination: Tuple[int, int]) -> Tuple[str, str, float]:
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                state.executor,
                find_duplicates_proc,
                preproc_files[combination[0]],
                preproc_files[combination[1]],
            )
            app.post_message(ProgressBarAdvance(1))
            return result
        except Exception as e:
            raise RuntimeError(e)

    app.info(f"Finding duplicates, checking {total_tasks} combinations")
    proc_tasks = [_proc(combination) for combination in file_combinations]
    results = await asyncio.gather(*proc_tasks)
    results = [r for r in results if r is not None and r[2] > 0.9]

    async def _unload(file: AudioFile) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(state.executor, file.unload)

    await asyncio.gather(*[_unload(file) for file in preproc_files])

    new_data = []
    for r in results:
        if r[2] > 0.9:
            new_data.append({"File": r[0], "File 2": r[1], "Similarity": r[2]})

    state.duplicate_data = pd.DataFrame(new_data)
    app.post_message(TableUpdate("find_duplicates"))
    if not state.duplicate_data.empty:
        app.info("Done finding duplicates")
    else:
        app.info("No duplicates found")
    state.executor.shutdown()
