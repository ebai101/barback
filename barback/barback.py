import audio_file


def check_loop(a: audio_file.AudioFile):
    file, is_loop, bpm, num_bars = a.is_loop()
    zc = a.get_start_end_zero_crossing()

    return file, is_loop, bpm, num_bars, zc
