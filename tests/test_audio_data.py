# type: ignore
from pathlib import Path

import pytest

from barback.audio_data import AudioData, AudioDataRow
from barback.audio_file import AudioFile
from barback.util.types import FinalizerIssue


@pytest.fixture
async def audio_files() -> tuple[AudioFile, AudioFile, AudioFile]:
    return (
        AudioFile(
            "testpack/Loops/Drum_Loops/Drum_Loops/JAFUNK_110_drum_loop_vintage.wav"
        ),
        AudioFile("testpack/Loops/Rhodes_Loops/JAFUNK_110_rhodes_loop_bliss_G#maj.wav"),
        AudioFile("testpack/One_Shots/Guitar/JAFUNK_guitar_lick_root_A.wav"),
    )


@pytest.fixture
async def sample_rows(
    audio_files: tuple[AudioFile, AudioFile, AudioFile]
) -> tuple[AudioDataRow, AudioDataRow, AudioDataRow]:
    file1, file2, file3 = audio_files
    row1 = AudioDataRow(
        file=file1,
        duration=8.72,
        sample_rate=44100,
        bit_depth="PCM_24",
        loop="yes",
        bpm=110,
        bars=4,
        zc="",
        finalizer_issues=[],
    )

    row2 = AudioDataRow(
        file=file2,
        duration=8.72,
        sample_rate=44100,
        bit_depth="PCM_24",
        loop="no (off by 1.27 samples)",
        bpm=110,
        bars=4,
        zc="",
        finalizer_issues=[FinalizerIssue("Loop", "does not loop")],
    )

    row3 = AudioDataRow(
        file=file3,
        duration=None,
        sample_rate=None,
        bit_depth=None,
        loop=None,
        bpm=None,
        bars=None,
        zc=None,
        finalizer_issues=None,
    )

    return row1, row2, row3


@pytest.fixture
async def audio_data() -> AudioData:
    return AudioData()


@pytest.fixture
async def populated_audio_data(
    audio_data: AudioData, sample_rows: tuple[AudioDataRow, AudioDataRow, AudioDataRow]
) -> AudioData:
    for row in sample_rows:
        audio_data.add_row(row)
    return audio_data


async def test_add_row(
    audio_data: AudioData, sample_rows: tuple[AudioDataRow, AudioDataRow, AudioDataRow]
):
    row1, row2, _ = sample_rows

    audio_data.add_row(row1)
    assert len(audio_data) == 1
    assert str(row1.file.filename) in audio_data

    audio_data.add_row(row2)
    assert len(audio_data) == 2
    assert str(row2.file.filename) in audio_data


async def test_get_row(
    audio_data: AudioData,
    audio_files: tuple[AudioFile, AudioFile, AudioFile],
    sample_rows: tuple[AudioDataRow, AudioDataRow, AudioDataRow],
):
    file1, _, _ = audio_files
    row1, _, _ = sample_rows

    assert audio_data.get_row(file1) is None

    audio_data.add_row(row1)
    retrieved_row = audio_data.get_row(file1)
    assert retrieved_row == row1

    assert audio_data.get_row(str(file1.filename)) == row1
    assert audio_data.get_row(Path(str(file1.filename))) == row1


async def test_get_files(
    populated_audio_data: AudioData, audio_files: tuple[AudioFile, AudioFile, AudioFile]
):
    file1, file2, _ = audio_files

    files = populated_audio_data.get_files()
    assert len(files) == 3
    assert file1 in files
    assert file2 in files


async def test_get_col(populated_audio_data: AudioData):
    bpms = populated_audio_data.get_col("bpm")
    assert len(bpms) == 3
    assert 110 in bpms
    assert None in bpms

    with pytest.raises(ValueError, match="Invalid column name"):
        populated_audio_data.get_col("invalid column")


async def test_update_row(
    audio_data: AudioData,
    audio_files: tuple[AudioFile, AudioFile, AudioFile],
    sample_rows: tuple[AudioDataRow, AudioDataRow, AudioDataRow],
):
    file1, _, _ = audio_files
    row1, _, _ = sample_rows

    audio_data.add_row(row1)

    assert audio_data.update_row(file1, bpm=160, duration=90.0)
    updated_row = audio_data.get_row(file1)
    assert updated_row.bpm == 160
    assert updated_row.duration == 90.0

    assert not audio_data.update_row("/non/existent/file.wav", bpm=100)


async def test_filter_by_dir(populated_audio_data: AudioData):
    filtered = populated_audio_data.filter_by_dir("testpack/One_Shots")
    assert len(filtered) == 1

    filtered = populated_audio_data.filter_by_dir("testpack/Loops")
    assert len(filtered) == 2

    filtered = populated_audio_data.filter_by_dir("non/existent")
    assert len(filtered) == 0


async def test_iteration(populated_audio_data, sample_rows):
    row1, row2, row3 = sample_rows

    rows = list(populated_audio_data)
    assert len(rows) == 3
    assert row1 in rows
    assert row2 in rows
    assert row3 in rows


async def test_contains(audio_data, audio_files, sample_rows):
    file1, _, _ = audio_files
    row1, _, _ = sample_rows

    assert file1 not in audio_data

    audio_data.add_row(row1)
    assert file1 in audio_data
    assert str(file1.filename) in audio_data
    assert Path(str(file1.filename)) in audio_data


async def test_empty_audio_data(audio_data):
    assert len(audio_data) == 0
    assert list(audio_data) == []
    assert audio_data.get_files() == []
    assert audio_data.get_col("bpm") == []


async def test_none_values(populated_audio_data):
    none_values = populated_audio_data.get_col("bpm")
    assert None in none_values

    filtered = populated_audio_data.filter_by_dir("testpack/One_Shots")
    assert len(filtered) == 1
    row = next(iter(filtered))
    assert row.bpm is None
    assert row.duration is None
