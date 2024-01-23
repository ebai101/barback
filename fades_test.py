import sys

import librosa

from audio_file import AudioFile

filename = sys.argv[1]
audio_file = AudioFile(
    filename, sample_rate=librosa.get_samplerate(filename), mono=False
)
print(audio_file.sample_rate)
audio_file.smart_fade()
audio_file.save()
