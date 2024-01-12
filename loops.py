import re
import os
import librosa


# checks if a splice formatted audio file loops properly
# returns a boolean (loopable/not loopable) and an error message if no BPM is found
def check_loop(filename):
    print(f"\n{os.path.basename(filename)}")
    audio, sr = librosa.load(filename)

    # find bpm - return if none found
    bpm_regex = re.search("([6-9][0-9](?![0-9])|[1-2][0-9][0-9])", filename)
    if bpm_regex is None:
        return False, "no bpm found in filename"
    else:
        bpm = int(bpm_regex.group(0))
    print(f"bpm: {bpm}")

    # calculate samples/bar (assuming 4 beats/bar) and number of bars
    bar_len_samples = sr * ((60 / bpm) * 4.0)
    num_bars = audio.shape[0] / bar_len_samples
    num_bars = round(num_bars)  # ideal bar length
    print(f"samples/bar: {bar_len_samples}")
    print(f"num bars: {num_bars}")

    # determine if sample is loopable
    # considered loopable if the remainder is within a whole sample
    remainder = audio.shape[0] % bar_len_samples
    if audio.shape[0] < (num_bars * bar_len_samples):
        remainder = audio.shape[0] - (num_bars * bar_len_samples)
    is_loopable = -1.0 < remainder < 1.0
    print(f"remainder: {remainder}")

    print(f"loopable: {is_loopable}")
    return is_loopable, ""


# testing stuff
if __name__ == "__main__":

    def file_gen(dir):
        for dirpath, _, filenames in os.walk(dir):
            for f in filenames:
                yield os.path.abspath(os.path.join(dirpath, f))

    test_dir = "/Volumes/FilesHDD/splice sessions/john/mad keys/Mad Keys - The Essentials/Loops/Melodic_Loops/Songstarter_Loops/"
    for file in file_gen(test_dir):
        check_loop(file)
