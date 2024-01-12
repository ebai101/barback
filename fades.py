import pywt
import librosa
import numpy as np
import soundfile as sf


# applies fades of a given type
def fade(buf, fade_dir, fade_type):
    if fade_dir not in ["in", "out"]:
        raise ValueError('fade_dir must be "in" or "out"')

    match fade_type:
        case "linear":
            fade = np.linspace(0, 1, len(buf))
        case "cosine":
            fade = 0.5 * np.cos(np.pi * np.linspace(1, 0, len(buf))) + 0.5
        case _:
            raise ValueError("unsupported fade_type")
            sys.exit(1)

    if fade_dir == "out":
        return buf * fade[::-1]
    return buf * fade


# perform smart fades on an audio object
def smart_fade(audio, sr, threshold=0.02):
    audio_mono = librosa.to_mono(audio)
    test_len = 512  # length of the testing buffer
    test_c = int(test_len / 2)  # center index of the testing buffer
    fade_array = 2 ** np.arange(1, 9, 1)  # 2-256, each value is double the last

    for fl in fade_array:
        # test buffer is last TEST_C samples + first TEST_C samples
        test_buf = np.concatenate((audio_mono[-test_c:], audio_mono[:test_c]))

        # apply fade out and fade in
        test_buf[test_c - fl : test_c] = fade(
            test_buf[test_c - fl : test_c], "out", "cosine"
        )
        test_buf[test_c : test_c + fl] = fade(
            test_buf[test_c : test_c + fl], "in", "cosine"
        )

        cA, cD2, cD1 = pywt.wavedec(
            librosa.util.normalize(test_buf), "db1", level=2
        )  # wavelet decomposition
        detail = cD2[
            int(len(cD2) * 3 / 8) : int(len(cD2) * 5 / 8)
        ]  # only the center of the 2nd level is of interest
        detail *= librosa.filters.get_window(
            "parzen", len(detail)
        )  # window to avoid false positives on the edges

        if np.max(np.abs(detail)) < threshold:
            print(f"fl of {fl} samples is long enough to prevent a click")

            # fade left channel
            audio[0][-fl:] = fade(audio[0][-fl:], "out", "cosine")
            audio[0][:fl] = fade(audio[0][:fl], "in", "cosine")

            # fade right channel
            audio[1][-fl:] = fade(audio[1][-fl:], "out", "cosine")
            audio[1][:fl] = fade(audio[1][:fl], "in", "cosine")

            return audio

    print("no suitable fl found")
    return audio
