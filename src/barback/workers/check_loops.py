import asyncio
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import cpu_count

from textual import work

from barback.audio_file import AudioFile
from barback.state import BarbackState
from barback.util.messages import ProgressBarAdvance, ProgressBarUpdate, TableUpdate
from barback.util.protocol import BarbackProtocol
from barback.util.types import LoopResponse


def check_loops_proc(af: AudioFile) -> tuple[LoopResponse, str]:
    af.load(mono=True)
    is_loop = af.is_loop()
    zc = af.get_start_end_zero_crossing()
    af.unload()

    return is_loop, zc


@work
async def check_one_loop(
    app: BarbackProtocol, state: BarbackState, af: AudioFile
) -> None:
    r = check_loops_proc(af)
    state.audio_data.update_row(
        r[0].filename, loop=r[0].response, bpm=r[0].bpm, bars=r[0].num_bars, zc=r[1]
    )
    app.post_message(TableUpdate("check_one_loop"))
    app.info("Done checking loops")


@work
async def check_loops(app: BarbackProtocol, state: BarbackState) -> None:
    state.executor = ProcessPoolExecutor(max_workers=cpu_count())

    files = state.audio_data.get_files()
    total_tasks = len(files)

    app.info("Checking loops")
    app.post_message(ProgressBarUpdate(total_tasks, 0))

    async def _proc(file: AudioFile) -> tuple[LoopResponse, str]:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(state.executor, check_loops_proc, file)
        app.post_message(ProgressBarAdvance(1))
        return result

    tasks = [_proc(file) for file in files]
    results = await asyncio.gather(*tasks)

    for r in results:
        ret_result = state.audio_data.update_row(
            r[0].filename,
            loop=r[0].response,
            bpm=r[0].bpm,
            bars=r[0].num_bars,
            zc=r[1],
        )
        continue

    app.post_message(TableUpdate("check_loops"))
    app.info("Done checking loops")
    state.executor.shutdown()
