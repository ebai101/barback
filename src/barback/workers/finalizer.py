import asyncio
import os
import re
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import cpu_count
from pathlib import Path

from textual import work

from barback.audio_file import AudioFile
from barback.state import BarbackState
from barback.util.messages import ProgressBarAdvance, ProgressBarUpdate, TableUpdate
from barback.util.protocol import BarbackProtocol
from barback.util.types import FinalizerIssue, FinalizerIssueKind


# wav, 44.1, 24 bit
def final_check_file_sr_bd(af: AudioFile) -> list[str]:
    issues = []

    extension = af.filename.suffix
    if extension != ".wav":
        issues.append("not a wav file")

    if af.sample_rate != 44100:
        issues.append(
            f"File {af.filename.name} sample rate {af.sample_rate} is incorrect"
        )

    if af.bit_depth != "PCM_24":
        issues.append(f"File {af.filename.name} bit depth {af.bit_depth} is incorrect")

    return issues


# no extra silence at start/end
def final_check_silence(af: AudioFile) -> list[str]:
    issues = []

    start, end = af.get_start_end_silence()
    if (
        "loop" not in str(af.filename) and start >= 500
    ):  # tighter restriction on one shots
        issues.append(f"{start} samples at the start")
    elif start >= 22050:
        issues.append(f"{start} samples at the start")
    if end >= 22050:
        issues.append(f"{end} samples at the end")

    return issues


# no clicks/pops at start/end
def final_check_start_end_zero_crossing(af: AudioFile) -> list[str]:
    nonzeros = af.get_start_end_zero_crossing()
    if nonzeros != "":
        return [f"nonzero values at {nonzeros}"]

    return []


# loops are proper loops
def final_check_loops(af: AudioFile) -> list[str]:
    if "loop" not in str(af.filename):
        return []
    is_loop = af.is_loop().is_loop
    if not is_loop:
        return ["does not loop"]
    return []


# tonal loops have key signature
def final_check_tonal_loop_key_signature(af: AudioFile) -> list[str]:
    issues = []

    # first check if there are multiple key signatures
    key_sig_regex = r"_[A-G][b#]?(maj|min)?"
    key_sig_matches = re.findall(key_sig_regex, os.path.basename(af.filename))
    if len(key_sig_matches) > 1:
        issues.append("multiple key signatures")

    # then, if the file is a loop, check that the key signature is at the end
    if "loop" not in str(af.filename).lower():
        return issues
    key_sig_at_end_regex = r"^.*_[A-G](?:#|b)?(?:maj|min)?(?:\.wav)?$"
    if not re.match(key_sig_at_end_regex, af.filename.name) and not any(
        s in str(af.filename).lower() for s in ["drum", "perc", "hihat"]
    ):
        issues.append("does not have a key signature but is a tonal loop")
    return issues


def finalizer_proc(af: AudioFile) -> tuple[Path, list[FinalizerIssue]]:
    issues = []
    af.load(mono=True)

    def append_issue(issue: FinalizerIssueKind, message: str) -> None:
        issues.append(FinalizerIssue(issue, message))

    for i in final_check_file_sr_bd(af):
        append_issue("SR/BD", i)
    for i in final_check_silence(af):
        append_issue("Silence", i)
    for i in final_check_start_end_zero_crossing(af):
        append_issue("ZC", i)
    for i in final_check_loops(af):
        append_issue("Loop", i)
    for i in final_check_tonal_loop_key_signature(af):
        append_issue("Key sig", i)

    af.unload()
    return af.filename, issues


@work
async def finalizer(app: BarbackProtocol, state: BarbackState) -> None:
    state.executor = ProcessPoolExecutor(max_workers=cpu_count())
    files = state.audio_data.get_files()
    total_tasks = len(files)
    app.info("Running finalizer")
    app.post_message(ProgressBarUpdate(total_tasks, 0))

    async def _proc(af: AudioFile) -> tuple[Path, list[FinalizerIssue]]:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(state.executor, finalizer_proc, af)
        app.post_message(ProgressBarAdvance(1))
        return result

    tasks = [_proc(file) for file in files]
    results = await asyncio.gather(*tasks)
    results_dict = {r[0]: r[1] for r in results}
    # results = [finalize(file) for file in files]

    for af in results_dict.keys():
        issues_list = results_dict[af]
        if len(issues_list) == 0:
            continue
        state.audio_data.update_row(af, finalizer_issues=issues_list)

    app.post_message(TableUpdate("finalizer"))
    app.info("Done running finalizer")

    state.executor.shutdown()
