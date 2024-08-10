#!/usr/bin/env python3

import itertools
import logging
import os
import sys
import time
import warnings
import select

from joblib import Parallel, delayed
from tabulate import tabulate
from tqdm import tqdm
from watchdog.events import PatternMatchingEventHandler
from watchdog.observers import Observer
from simple_colors import *

from audio_file import AudioFile


# finds valid audio files in a directory
def find_valid_audio_files(audio_dir):
    valid_extensions = (".mp3", ".flac", ".wav", ".aif")
    if os.path.isdir(audio_dir):
        try:
            files = [
                os.path.join(audio_dir, f)
                for f in os.listdir(audio_dir)
                if f.endswith(valid_extensions)
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
        zc = a.start_end_zero_crossing()

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
    # [
    #     r
    #     for r in tqdm(
    #         Parallel(return_as="generator", n_jobs=-1)(
    #             delayed(_proc)(a) for a in audios
    #         ),
    #         total=len(audios),
    #         desc="Extending audio files",
    #     )
    # ]
    print("done")
    sys.exit(0)


def colorized_loop_table(data, headers):
    colored_data = []
    for row in data:
        if "no" in row[1] or row[1] == "no bpm found":
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
    if action == "duplicates":
        print(f"Finding duplicates for {audio_dir}")
        find_duplicates(audio_files)
    elif action == "loops":
        print(f"Checking loops for {audio_dir}")
        check_loops(audio_files)
    elif action == "extend":
        print(f"Extending samples in {audio_dir} with bpm {bpm}")
        extend(audio_files, bpm)
    end_time = time.time() - start_time
    print(f"done in {end_time} sec")


class WatchdogHandler(PatternMatchingEventHandler):
    def __init__(self):
        super(WatchdogHandler, self).__init__(
            patterns=("*.mp3", "*.flac", "*.wav", "*.aif", "*.aiff")
        )

    def on_moved(self, event):
        if not ".tmp" in event.dest_path and not "RX Temp Save File" in event.dest_path:
            main(action, audio_dir)

    def on_modified(self, event):
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

    # rerun on file changes
    event_handler = WatchdogHandler()
    observer = Observer()
    observer.schedule(event_handler, audio_dir, recursive=True)
    observer.start()
    try:
        while True:
            if select.select([sys.stdin], [], [], 0.1)[0]:
                user_input = ""
                if user_input == "":
                    main(action, audio_dir)
                while select.select([sys.stdin], [], [], 0)[0]:
                    sys.stdin.readline()
            time.sleep(0.1)
    except KeyboardInterrupt:
        observer.stop()
    finally:
        observer.join()
