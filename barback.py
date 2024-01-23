#!/usr/bin/env python3

import os
import sys
import time
import logging
import warnings
import itertools
from tqdm import tqdm
from tabulate import tabulate
from audio_file import AudioFile
from joblib import Parallel, delayed
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler


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
        res = a.is_loop()
        # print(res)
        return res

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
        [(r[0].filename_to_link(), r[1], r[2], r[3]) for r in result if r[1]],
        key=lambda x: x[0],
    )
    print(tabulate(loops, headers=["file", "is_loop", "bpm", "num_bars"]))


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


def main(action, audio_dir):
    start_time = time.time()
    os.system("cls" if os.name == "nt" else "clear")
    audio_files = find_valid_audio_files(audio_dir)
    if action == "duplicates":
        print(f"Finding duplicates for {audio_dir}")
        find_duplicates(audio_files)
    elif action == "loops":
        print(f"Checking loops for {audio_dir}")
        check_loops(audio_files)
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

    # run once
    main(action, audio_dir)

    # rerun on file changes
    event_handler = WatchdogHandler()
    observer = Observer()
    observer.schedule(event_handler, audio_dir, recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    finally:
        observer.join()
