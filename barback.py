#!/usr/bin/env python3

import itertools
import logging
import os
import select
import sys
import time
import urllib
import warnings

from joblib import Parallel, delayed
from simple_colors import *
from tabulate import tabulate
from tqdm import tqdm
from watchdog.events import PatternMatchingEventHandler
from watchdog.observers import Observer

from audio_file import AudioFile


def open_in_rx_link(label, filenames):
    if len(filenames) == 0:
        logging.error("open_in_rx_link received an empty filename list")
        return

    uri = "kmtrigger://macro=79D7F9AF-3E50-4F43-A602-4BE82B07240D"
    for fn in filenames:
        uri.append("&value={}".format(urllib.parse.quote(fn, safe="")))
    return f"\033]8;;{uri}\033\\{label}\033]8;;\033\\"


# finds valid audio files in a directory
def find_valid_audio_files(audio_dir):
    valid_extensions = (".mp3", ".flac", ".wav", ".aif", ".aiff")

    if os.path.isdir(audio_dir):
        try:
            files = [
                os.path.join(root, file)
                for root, _, files in os.walk(audio_dir)
                for file in files
                if file.lower().endswith(valid_extensions)
            ]
        except FileNotFoundError as e:
            logging.error(f"Error opening file: {e}")
            return None
    else:
        logging.error("Must specify a directory")
        return None

    return files


def check_loops(audio_files):
    # preprocessing
    audios = [
        r
        for r in tqdm(
            Parallel(return_as="generator", n_jobs=-1)(
                delayed(AudioFile)(f) for f in audio_files
            ),
            total=len(audio_files),
            desc="Preprocessing",
        )
    ]

    # check for loops
    def _proc(a):
        file, is_loop, bpm, num_bars = a.is_loop()
        zc = a.get_start_end_zero_crossing()

        # print(res)
        return file, is_loop, bpm, num_bars, zc

    result = [
        r
        for r in tqdm(
            Parallel(return_as="generator", n_jobs=-1)(
                delayed(_proc)(c) for c in audios
            ),
            total=len(audios),
            desc="Checking for loops",
        )
    ]
    loops = sorted(
        [[r[0].filename_to_link(), r[1], r[2], r[3], r[4]] for r in result if r[1]],
        key=lambda x: x[0],
    )

    print(
        colorized_loop_table(
            loops, headers=["file", "is_loop", "bpm", "num_bars", "zero_crossings"]
        )
    )


def find_duplicates(audio_files):
    # preprocessing
    def _preproc(f):
        warnings.filterwarnings("ignore", category=UserWarning, module="librosa")
        a = AudioFile(f)
        a.zero_crossings = a.calc_zero_crossings()
        a.chroma = a.calc_chroma()
        a.spectral_contrast = a.calc_spectral_contrast()
        return a

    audios = [
        r
        for r in tqdm(
            Parallel(return_as="generator", n_jobs=-1)(
                delayed(_preproc)(f) for f in audio_files
            ),
            total=len(audio_files),
            desc="Preprocessing",
        )
    ]

    # create list of comparison combinations, to avoid redundant checks
    combinations = list(
        (i, j) for ((i, _), (j, _)) in itertools.combinations(enumerate(audios), 2)
    )

    # check similarity
    def _proc(c):
        s = audios[c[0]].weighted_similarity(audios[c[1]])
        # print(s)
        return s

    result = [
        r
        for r in tqdm(
            Parallel(return_as="generator", n_jobs=-1)(
                delayed(_proc)(c) for c in combinations
            ),
            total=len(combinations),
            desc="Checking similarity",
        )
    ]

    likely_dupes = sorted(
        [
            (r[0].filename_to_link(), r[1].filename_to_link(), r[2])
            for r in result
            if r[2] > 0.99
        ],
        key=lambda x: x[2],
        reverse=True,
    )
    possible_dupes = sorted(
        [
            (r[0].filename_to_link(), r[1].filename_to_link(), r[2])
            for r in result
            if r[2] > 0.9 and r[2] < 0.99
        ],
        key=lambda x: x[2],
        reverse=True,
    )

    if len(likely_dupes) > 0:
        print("\nLikely Duplicates:")
        print(tabulate(likely_dupes, headers=["file 1", "file 2", "similarity"]))
    if len(possible_dupes) > 0:
        print("\nPossible Duplicates:")
        print(tabulate(possible_dupes, headers=["file 1", "file 2", "similarity"]))


def extend(audio_files, bpm):
    # preprocessing
    def _preproc(f):
        warnings.filterwarnings("ignore", category=UserWarning, module="librosa")
        a = AudioFile(f, sample_rate=None, mono=False, bpm=int(bpm))
        a.first_onset = a.calc_first_onset()
        return a

    audios = [
        r
        for r in tqdm(
            Parallel(return_as="generator", n_jobs=-1)(
                delayed(_preproc)(f) for f in audio_files
            ),
            total=len(audio_files),
            desc="Preprocessing",
        )
    ]

    def _proc(a):
        if bpm == "infer":
            a.extend(infer=True)
        else:
            a.extend()

    for a in audios:
        _proc(a)

    print("done")
    sys.exit(0)


def final_check(audio_files):
    import audio_file_checks

    print("Before running this:")
    print("- ensure all files are named to spec")
    print("- ensure all folders are properly organized")

    # preprocessing
    def _preproc(f):
        warnings.filterwarnings("ignore", category=UserWarning, module="librosa")
        a = AudioFile(f)
        return a

    audios = [
        r
        for r in tqdm(
            Parallel(return_as="generator", n_jobs=-1)(
                delayed(_preproc)(f) for f in audio_files
            ),
            total=len(audio_files),
            desc="Preprocessing",
        )
    ]

    # wav, 44.1, 24 bit
    sr_bd_results = [
        r
        for r in tqdm(
            Parallel(return_as="generator", n_jobs=-1)(
                delayed(audio_file_checks.check_file_sr_bd)(c) for c in audios
            ),
            total=len(audios),
            desc="Checking sample rate and bit depth",
        )
        if r != ""
    ]

    # no extra silence at start/end
    silence_results = [
        r
        for r in tqdm(
            Parallel(return_as="generator", n_jobs=-1)(
                delayed(audio_file_checks.check_silence)(c) for c in audios
            ),
            total=len(audios),
            desc="Checking for start/end silence",
        )
        if r != ""
    ]

    # all the loops are loopy
    loop_results = [
        r
        for r in tqdm(
            Parallel(return_as="generator", n_jobs=-1)(
                delayed(audio_file_checks.check_loops)(c) for c in audios
            ),
            total=len(audios),
            desc="Checking loops",
        )
        if r != ""
    ]

    # tonal loops have key signature
    key_sig_results = [
        r
        for r in tqdm(
            Parallel(return_as="generator", n_jobs=-1)(
                delayed(audio_file_checks.check_tonal_loop_key_signature)(c)
                for c in audios
            ),
            total=len(audios),
            desc="Checking for key signatures in tonal loops",
        )
        if r != ""
    ]

    # no clicks/pops at start/end
    zc_results = [
        r
        for r in tqdm(
            Parallel(return_as="generator", n_jobs=-1)(
                delayed(audio_file_checks.check_start_end_zero_crossing)(c)
                for c in audios
            ),
            total=len(audios),
            desc="Checking zero crossings at start/end",
        )
        if r != ""
    ]

    # open_in_rx_names = []

    if len(sr_bd_results) > 0:
        print(cyan(f"Samplerate/bit depth issues ({len(sr_bd_results)}):"))
        [print(r) for r in sr_bd_results if r != ""]

    if len(silence_results) > 0:
        print(cyan(f"Silence issues ({len(silence_results)}):"))
        [print(r) for r in silence_results if r != ""]
        # open_in_rx_names.append(open_in_rx_link("silence"))

    if len(loop_results) > 0:
        print(cyan(f"Loop issues ({len(loop_results)}):"))
        [print(r) for r in loop_results if r != ""]

    if len(key_sig_results) > 0:
        print(cyan(f"Key signature issues ({len(key_sig_results)}):"))
        [print(r) for r in key_sig_results if r != ""]

    if len(zc_results) > 0:
        print(cyan(f"Start/end zero crossing issues ({len(zc_results)}):"))
        [print(r) for r in zc_results if r != ""]
        # open_in_rx_names.append("zero crossing")

    # if len(open_in_rx_names) > 0:
    #     line = "open in rx: "
    #     print(f"open in rx: ")


def colorized_loop_table(data, headers):
    colored_data = []
    for row in data:
        if not "yes" in row[1]:
            colored_row = [red(str(cell)) for cell in row]
        elif row[4] != "":
            colored_row = [yellow(str(cell)) for cell in row]
        elif row[3] % 2 != 0:
            colored_row = [cyan(str(cell)) for cell in row]
        else:
            colored_row = [str(cell) for cell in row]
        colored_data.append(colored_row)
    return tabulate(colored_data, headers=headers)


def main(action, audio_dir, bpm=120):
    start_time = time.time()
    os.system("cls" if os.name == "nt" else "clear")
    audio_files = find_valid_audio_files(audio_dir)
    if audio_files == None:
        sys.exit(1)

    if action == "duplicates":
        print(f"Finding duplicates for {audio_dir}")
        find_duplicates(audio_files)
    elif action == "loops":
        print(f"Checking loops for {audio_dir}")
        check_loops(audio_files)
    elif action == "extend":
        print(f"Extending samples in {audio_dir} with bpm {bpm}")
        extend(audio_files, bpm)
    elif action == "finalcheck":
        print(f"Doing a final check for {audio_dir}")
        final_check(audio_files)
    end_time = time.time() - start_time
    print(f"done in {end_time} sec")


class WatchdogHandler(PatternMatchingEventHandler):
    def __init__(self):
        super(WatchdogHandler, self).__init__(
            patterns=("*.mp3", "*.flac", "*.wav", "*.aif", "*.aiff")
        )

    def on_moved(self, event):
        return
        if not ".tmp" in event.dest_path and not "RX Temp Save File" in event.dest_path:
            main(action, audio_dir)

    def on_modified(self, event):
        return
        main(action, audio_dir)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("specify an action and a folder")
        sys.exit(1)
    action = sys.argv[1]
    audio_dir = os.path.abspath(sys.argv[2])
    if action == "extend":
        if len(sys.argv) < 4:
            print("specify an action, folder and bpm")
            sys.exit(1)
        bpm = sys.argv[3]
        main(action, audio_dir, bpm)
    else:
        main(action, audio_dir)

    # rerun on file changes or enter press
    event_handler = WatchdogHandler()
    observer = Observer()
    observer.schedule(event_handler, audio_dir, recursive=True)
    observer.start()
    try:
        while True:
            if select.select([sys.stdin], [], [], 0.1)[0]:
                main(action, audio_dir)
                while select.select([sys.stdin], [], [], 0)[0]:
                    sys.stdin.readline()
            time.sleep(0.1)
    except KeyboardInterrupt:
        observer.stop()
    finally:
        observer.join()
