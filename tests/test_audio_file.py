# type: ignore
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import numpy as np
import pytest

from barback.audio_file import AudioFile, AudioFileError
from barback.util.types import LoopResponse

# Test data
SAMPLE_RATE = 44100
DURATION = 8.0
BIT_DEPTH = "PCM_24"
MONO_AUDIO = np.sin(
    np.linspace(0, 440 * 2 * np.pi * DURATION, int(SAMPLE_RATE * DURATION))
)
STEREO_AUDIO = np.vstack((MONO_AUDIO, MONO_AUDIO))


class MockSoundFileInfo:
    def __init__(self, subtype="PCM_24"):
        self.subtype = subtype


def create_mock_librosa():
    mock = MagicMock()

    # Basic properties
    mock.get_duration.return_value = DURATION
    mock.get_samplerate.return_value = SAMPLE_RATE

    # Loading function
    def mock_load(path, sr=None, mono=False):
        if mono:
            return MONO_AUDIO, sr or SAMPLE_RATE
        return STEREO_AUDIO, sr or SAMPLE_RATE

    mock.load.side_effect = mock_load

    # Audio processing functions
    mock.to_mono.return_value = MONO_AUDIO
    mock.onset.onset_detect.return_value = np.array([100])
    mock.feature.chroma_cqt.return_value = np.zeros((12, 100))
    mock.feature.spectral_contrast.return_value = np.zeros((7, 100))

    # Effects
    def mock_trim(y, top_db=75):
        # Return trimmed audio and indices
        return y, np.array([0, len(y)])

    mock.effects.trim.side_effect = mock_trim

    return mock


@pytest.fixture
def mock_properties():
    """Fixture to mock all property-decorated methods"""
    patches = [
        patch("barback.audio_file.librosa.get_duration", return_value=DURATION),
        patch("barback.audio_file.librosa.get_samplerate", return_value=SAMPLE_RATE),
        patch("barback.audio_file.sf.info", return_value=MockSoundFileInfo(BIT_DEPTH)),
    ]

    for p in patches:
        p.start()

    yield {"duration": DURATION, "sample_rate": SAMPLE_RATE, "bit_depth": BIT_DEPTH}

    for p in patches:
        p.stop()


@pytest.fixture
def mock_librosa():
    """Fixture to mock librosa functions"""
    with patch("barback.audio_file.librosa", new_callable=create_mock_librosa) as mock:
        yield mock


@pytest.fixture
def mock_soundfile():
    """Fixture to mock soundfile functions"""
    with patch("barback.audio_file.sf") as mock:
        mock.info.return_value = MockSoundFileInfo(BIT_DEPTH)
        mock.write = Mock()
        yield mock


@pytest.fixture
async def audio_file(mock_properties):
    """Fixture for basic AudioFile instance"""
    return AudioFile(Path("/path/to/DRUMS_120_test.wav"))


@pytest.fixture
async def loaded_audio_file(audio_file, mock_librosa):
    """Fixture for loaded AudioFile instance"""
    audio_file.load()
    return audio_file


@pytest.fixture
async def stereo_audio_file(mock_properties, mock_librosa):
    """Fixture for stereo AudioFile instance"""
    with patch(
        "barback.audio_file.librosa.load", return_value=(STEREO_AUDIO, SAMPLE_RATE)
    ):
        af = AudioFile(Path("/path/to/DRUMS_120_stereo.wav"))
        af.load()
        return af


async def test_init(audio_file):
    """Test AudioFile initialization"""
    assert isinstance(audio_file.filename, Path)
    assert not audio_file.loaded
    assert str(audio_file.filename) == "/path/to/DRUMS_120_test.wav"


async def test_str_representation(audio_file):
    """Test string representation of AudioFile"""
    assert str(audio_file) == "DRUMS_120_test.wav"


async def test_properties(audio_file, mock_properties):
    """Test all property-decorated methods"""
    assert audio_file.duration == mock_properties["duration"]
    assert audio_file.sample_rate == mock_properties["sample_rate"]
    assert audio_file.bit_depth == mock_properties["bit_depth"]


async def test_properties_error_handling():
    """Test property error handling"""
    with patch(
        "barback.audio_file.librosa.get_duration",
        side_effect=Exception("Duration error"),
    ):
        with patch(
            "barback.audio_file.librosa.get_samplerate",
            side_effect=Exception("Sample rate error"),
        ):
            with patch(
                "barback.audio_file.sf.info", side_effect=Exception("Bit depth error")
            ):
                audio_file = AudioFile(Path("test.wav"))

                with pytest.raises(Exception, match="Duration error"):
                    _ = audio_file.duration

                with pytest.raises(Exception, match="Sample rate error"):
                    _ = audio_file.sample_rate

                with pytest.raises(Exception, match="Bit depth error"):
                    _ = audio_file.bit_depth


async def test_load_unload(audio_file, mock_librosa, mock_properties):
    """Test loading and unloading audio"""
    # Test basic loading
    audio_file.load()
    assert audio_file.loaded
    assert hasattr(audio_file, "audio")
    mock_librosa.load.assert_called_once()

    # Test loading with specific sample rate
    audio_file.unload()
    audio_file.load(sample_rate=22050)
    mock_librosa.load.assert_called_with(audio_file.filename, sr=22050, mono=False)

    # Test loading already loaded file
    with pytest.raises(AudioFileError, match="Tried to load already loaded file"):
        audio_file.load()

    # Test unloading
    audio_file.unload()
    assert not audio_file.loaded
    assert not hasattr(audio_file, "audio")

    # Test unloading already unloaded file
    with pytest.raises(AudioFileError, match="Tried to unload non-loaded audio file"):
        audio_file.unload()


async def test_load_with_params(audio_file, mock_librosa):
    """Test loading with different parameters"""
    # Test mono loading
    audio_file.load(mono=True, sample_rate=44100)

    call_args = mock_librosa.load.call_args
    assert call_args.kwargs["mono"] == True
    assert call_args.kwargs["sr"] == 44100

    assert isinstance(audio_file.audio, np.ndarray)
    assert audio_file.audio.shape == MONO_AUDIO.shape


async def test_zero_crossings(loaded_audio_file):
    """Test zero crossings calculation"""
    zc = loaded_audio_file.zero_crossings
    assert isinstance(zc, float)
    assert 0 <= zc <= 1  # Zero crossing rate should be between 0 and 1

    # Test unloaded file
    audio_file = AudioFile(Path("test.wav"))
    with pytest.raises(AudioFileError, match="is not loaded"):
        zc = audio_file.zero_crossings


async def test_audio_features(loaded_audio_file, mock_librosa):
    """Test audio feature calculations"""
    # Test chroma
    chroma = loaded_audio_file.chroma
    assert isinstance(chroma, np.ndarray)
    assert chroma.shape == (12, 100)  # Check expected shape
    mock_librosa.feature.chroma_cqt.assert_called_once()

    # Test spectral contrast
    spectral = loaded_audio_file.spectral_contrast
    assert isinstance(spectral, np.ndarray)
    assert spectral.shape == (7, 100)  # Check expected shape
    mock_librosa.feature.spectral_contrast.assert_called_once()

    # Test first onset
    onset = loaded_audio_file.first_onset
    assert isinstance(onset, int)
    assert onset == 100  # Check mock value
    mock_librosa.onset.onset_detect.assert_called_once()


async def test_is_loop(loaded_audio_file, mock_properties):
    """Test loop detection"""

    length = int(SAMPLE_RATE * 2)
    loaded_audio_file.audio = np.zeros(length)

    # Test valid BPM in filename
    response = loaded_audio_file.is_loop()
    assert isinstance(response, LoopResponse)
    assert response.bpm == 120
    assert response.is_loop is True

    # Test different BPM values and filenames
    test_cases = [
        ("DRUMS_60_test.wav", True, "yes"),  # Minimum valid BPM
        ("DRUMS_299_test.wav", False, "no"),  # Maximum valid BPM
        ("DRUMS_59_test.wav", False, "bpm out of range"),  # Too low BPM
        ("DRUMS_300_test.wav", False, "bpm out of range"),  # Too high BPM
        ("DRUMS_test.wav", False, "no bpm found"),  # Missing BPM
        ("DRUMS_12X_test.wav", False, "no bpm found"),  # Invalid BPM format
        ("PREFIX_DRUMS_120_test.wav", True, "yes"),  # Valid BPM with prefix
        ("DRUMS_120_SUFFIX_test.wav", True, "yes"),  # Valid BPM with suffix
    ]

    for filename, expected_loop, expected_response in test_cases:
        audio_file = AudioFile(Path(filename))
        audio_file.audio = MONO_AUDIO
        audio_file.loaded = True

        response = audio_file.is_loop()
        assert response.is_loop == expected_loop
        assert expected_response in response.response

    # Test unloaded audio file
    loaded_audio_file.unload()
    with pytest.raises(AudioFileError, match="is not loaded"):
        loaded_audio_file.is_loop()


async def test_get_start_end_zero_crossing(loaded_audio_file, stereo_audio_file):
    """Test start/end zero crossing detection"""
    # Test with various array patterns
    test_cases = [
        (np.array([0.0, 0.0]), ""),  # No crossings
        (np.array([0.1, -0.1]), "start,end"),  # Both crossings
        (np.array([0.1, 0.0]), "start"),  # Start only
        (np.array([0.0, 0.1]), "end"),  # End only
    ]

    for audio, expected in test_cases:
        loaded_audio_file.audio = audio
        result = loaded_audio_file.get_start_end_zero_crossing(threshold=0.05)
        assert result == expected


async def test_get_start_end_zero_crossing_unloaded(audio_file, mock_properties):
    with pytest.raises(
        AudioFileError,
        match=f"{audio_file.filename} is not loaded",
    ):
        audio_file.get_start_end_zero_crossing()


async def test_get_start_end_silence(loaded_audio_file, mock_librosa):
    """Test silence detection at start and end of audio file"""
    # Test case 1: Silence at both ends
    # Mock librosa's frame detection to indicate silence at both ends
    mock_librosa.effects._signal_to_frame_nonsilent.return_value = np.array(
        [0, 0, 1, 1, 1, 0, 0]  # First and last frames are silent
    )
    mock_librosa.core.frames_to_samples.side_effect = (
        lambda x: x * 512
    )  # Typical hop length
    mock_librosa.to_mono.return_value = np.zeros(3584)  # 7 frames * 512 samples

    start, end = loaded_audio_file.get_start_end_silence()
    assert start == 1024  # 2 frames * 512 samples
    assert end == 1024  # 2 frames * 512 samples

    # Test case 2: No silence
    mock_librosa.effects._signal_to_frame_nonsilent.return_value = np.array(
        [1, 1, 1, 1, 1]  # All frames contain signal
    )
    mock_librosa.to_mono.return_value = np.zeros(2560)  # 5 frames * 512 samples

    start, end = loaded_audio_file.get_start_end_silence()
    assert start == 0
    assert end == 0

    # Test case 3: All silence
    mock_librosa.effects._signal_to_frame_nonsilent.return_value = np.array(
        [0, 0, 0, 0, 0]  # All frames are silent
    )
    audio_length = 2560  # 5 frames * 512 samples
    mock_librosa.to_mono.return_value = np.zeros(audio_length)

    start, end = loaded_audio_file.get_start_end_silence()
    assert start == 0
    assert end == audio_length

    # Test case 4: Only start silence
    mock_librosa.effects._signal_to_frame_nonsilent.return_value = np.array(
        [0, 0, 1, 1, 1]  # First two frames are silent
    )
    mock_librosa.to_mono.return_value = np.zeros(2560)

    start, end = loaded_audio_file.get_start_end_silence()
    assert start == 1024  # 2 frames * 512 samples
    assert end == 0

    # Test case 5: Only end silence
    mock_librosa.effects._signal_to_frame_nonsilent.return_value = np.array(
        [1, 1, 1, 0, 0]  # Last two frames are silent
    )
    mock_librosa.to_mono.return_value = np.zeros(2560)

    start, end = loaded_audio_file.get_start_end_silence()
    assert start == 0
    assert end == 1024  # 2 frames * 512 samples

    # Test unloaded file
    audio_file = AudioFile(Path("test.wav"))
    with pytest.raises(AudioFileError, match="is not loaded"):
        audio_file.get_start_end_silence()


async def test_save(loaded_audio_file, mock_soundfile, mock_properties):
    """Test saving audio file"""
    # Test mono audio save
    loaded_audio_file.audio = MONO_AUDIO
    loaded_audio_file.save()
    mock_soundfile.write.assert_called_once()

    # Test stereo audio save
    loaded_audio_file.audio = STEREO_AUDIO
    loaded_audio_file.save()
    assert mock_soundfile.write.call_count == 2

    # Test unloaded file
    audio_file = AudioFile(Path("test.wav"))
    with pytest.raises(AudioFileError, match="is not loaded"):
        audio_file.save()


async def test_sorting():
    """Test sorting functionality"""
    files = [
        AudioFile(Path("DRUMS_140_test.wav")),
        AudioFile(Path("DRUMS_120_test.wav")),
        AudioFile(Path("test.wav")),  # No BPM
        AudioFile(Path("DRUMS_130_test.wav")),
        AudioFile(Path("OTHER_140_test.wav")),  # Different prefix
    ]

    sorted_files = sorted(files)
    # Files with BPM should come first, in BPM order
    assert str(sorted_files[0].filename) == "DRUMS_120_test.wav"
    assert str(sorted_files[1].filename) == "DRUMS_130_test.wav"
    assert str(sorted_files[2].filename) == "DRUMS_140_test.wav"
    assert str(sorted_files[3].filename) == "OTHER_140_test.wav"
    # Files without BPM should come last
    assert str(sorted_files[4].filename) == "test.wav"


async def test_comparison_operators():
    """Test comparison operators"""
    file1 = AudioFile(Path("DRUMS_120_test.wav"))
    file2 = AudioFile(Path("DRUMS_140_test.wav"))
    file3 = AudioFile(Path("DRUMS_120_test.wav"))
    file4 = AudioFile(Path("test.wav"))  # No BPM

    # Test all comparison operators
    assert file1 < file2
    assert file2 > file1
    assert file1 == file3
    assert file1 != file2
    assert file1 <= file2
    assert file1 <= file3
    assert file2 >= file1
    assert file1 >= file3

    # Test comparisons with non-BPM files
    assert file1 < file4  # Files with BPM come before files without
    assert file4 > file1


async def test_load_error_handling(audio_file, mock_properties):
    """Test load error handling"""
    # Test generic error
    with patch("barback.audio_file.librosa.load", side_effect=Exception("Load error")):
        with pytest.raises(AudioFileError, match="Unexpected error loading file"):
            audio_file.load()

    # Test specific error types
    errors = [
        ValueError("Value error"),
        IOError("IO error"),
        RuntimeError("Runtime error"),
    ]

    for error in errors:
        with patch("barback.audio_file.librosa.load", side_effect=error):
            with pytest.raises(AudioFileError) as exc_info:
                audio_file.load()
            assert str(error) in str(exc_info.value)


async def test_feature_calculation_error_handling(audio_file):
    """Test error handling in feature calculation methods"""
    with patch(
        "barback.audio_file.librosa.feature.chroma_cqt",
        side_effect=Exception("is not loaded"),
    ):
        with pytest.raises(Exception, match="is not loaded"):
            c = audio_file.chroma

    with patch(
        "barback.audio_file.librosa.feature.spectral_contrast",
        side_effect=Exception("is not loaded"),
    ):
        with pytest.raises(Exception, match="is not loaded"):
            sc = audio_file.spectral_contrast

    with patch(
        "barback.audio_file.librosa.onset.onset_detect",
        side_effect=Exception("is not loaded"),
    ):
        with pytest.raises(Exception, match="is not loaded"):
            fo = audio_file.first_onset


async def test_is_loop_sample_accuracy(mock_properties):
    """Test loop detection sample accuracy"""
    test_cases = [
        (SAMPLE_RATE * 4, True),  # Exactly 2 bars at 120 BPM
        (SAMPLE_RATE * 4 + 1, False),  # 1 sample too long
        (SAMPLE_RATE * 4 - 1, False),  # 1 sample too short
        (SAMPLE_RATE * 2, True),  # Exactly 1 bar
    ]

    for num_samples, should_loop in test_cases:
        audio_file = AudioFile(Path("DRUMS_120_test.wav"))
        audio_file.audio = np.zeros(int(num_samples))
        audio_file.loaded = True

        response = audio_file.is_loop()
        assert response.is_loop == should_loop
        if should_loop:
            assert "yes" in response.response
        else:
            assert "no" in response.response


async def test_complex_filenames(mock_properties):
    """Test handling of complex filenames"""
    test_cases = [
        "DRUMS_120_test.wav",  # Standard format
        "prefix_DRUMS_120_test.wav",  # With prefix
        "DRUMS_120_suffix_test.wav",  # With suffix
        "prefix_DRUMS_120_suffix_test.wav",  # With both
        "Complex_DRUMS_120_V2_Final.wav",  # Complex naming
    ]

    for filename in test_cases:
        audio_file = AudioFile(Path(filename))
        audio_file.audio = MONO_AUDIO
        audio_file.loaded = True

        response = audio_file.is_loop()
        assert response.is_loop
        assert response.bpm == 120


async def test_zero_crossing_thresholds(loaded_audio_file):
    """Test zero crossing detection with different thresholds"""
    thresholds = [0.0, 0.01, 0.05, 0.1, 0.5, 1.0]

    for threshold in thresholds:
        result = loaded_audio_file.get_start_end_zero_crossing(threshold=threshold)
        assert result in ["", "start", "end", "start,end"]


async def test_get_sort_key():
    """Test internal sort key generation"""
    test_cases = [
        ("DRUMS_120_test.wav", (0, 120)),
        ("DRUMS_140_test.wav", (0, 140)),
        ("prefix_DRUMS_120_test.wav", (0, 120)),
    ]

    for filename, expected_key in test_cases:
        audio_file = AudioFile(Path(filename))
        assert audio_file._get_sort_key() == expected_key


async def test_comparison_not_implemented():
    """Test comparison operators when comparing with non-AudioFile objects"""
    audio_file = AudioFile(Path("DRUMS_120_test.wav"))

    assert audio_file.__eq__("DRUMS_120_test.wav") is NotImplemented
    assert audio_file.__eq__(123) is NotImplemented
    assert audio_file.__eq__(None) is NotImplemented
    assert audio_file.__eq__(Path("DRUMS_120_test.wav")) is NotImplemented

    assert audio_file.__ne__("DRUMS_120_test.wav") is NotImplemented
    assert audio_file.__ne__(123) is NotImplemented
    assert audio_file.__ne__(None) is NotImplemented
    assert audio_file.__ne__(Path("DRUMS_120_test.wav")) is NotImplemented

    # Verify that the Python interpreter handles NotImplemented correctly
    # by falling back to the built-in behavior
    assert (audio_file == "DRUMS_120_test.wav") is False
    assert (audio_file != "DRUMS_120_test.wav") is True
