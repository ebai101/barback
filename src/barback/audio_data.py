from collections.abc import Iterator
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

from barback.audio_file import AudioFile
from barback.util.types import Issue


@dataclass
class AudioDataRow:
    file: AudioFile
    duration: float | None = None
    sample_rate: float | None = None
    bit_depth: str | None = None
    loop: str | None = None
    bpm: int | None = None
    bars: int | None = None
    zc: str | None = None
    issues: list[Issue] | None = None


class AudioData:
    def __init__(self) -> None:
        self._data: dict[str, AudioDataRow] = {}
        self.logger = get_logger()

    def add_row(self, row: AudioDataRow) -> None:
        """Add a new row to the table."""
        self.logger.debug(f"Adding row to AudioData: {row.file.filename.name}")
        self._data[str(row.file.filename)] = row

    def get_row(self, file: str | Path | AudioFile) -> AudioDataRow | None:
        """Get a row by file path."""
        if isinstance(file, AudioFile):
            path = str(file.filename)
        else:
            path = str(file)
        return self._data.get(path)

    def get_files(self) -> list[AudioFile]:
        """Gets all the AudioFiles in the table."""
        return self.get_col("file")

    def get_col(self, column: str):
        """Get values from the specified column for all rows."""
        valid_fields = {f.name for f in fields(AudioDataRow)}
        if column not in valid_fields:
            raise ValueError(
                f"Invalid column name: {column}. Valid columns are: {valid_fields}"
            )

        return [getattr(row, column) for row in self._data.values()]

    def update_row(self, file: str | Path | AudioFile, **kwargs: Any | None) -> bool:
        """
        Update an existing row with new values.
        Returns True if the row was found and updated, False otherwise.
        """
        if isinstance(file, AudioFile):
            key = str(file.filename)
        else:
            key = str(file)

        if key in self._data:
            self.logger.debug(
                f"Updating row in AudioData: {Path(key).name} - {kwargs.keys()}"
            )
            row = self._data[key]
            valid_fields = {f.name for f in fields(AudioDataRow)}
            for attr, value in kwargs.items():
                if attr in valid_fields:
                    setattr(row, attr, value)
            return True
        return False

    def filter_by_dir(self, directory: str | Path) -> "AudioData":
        """Return a new table containing only rows where the file is in the specified directory."""
        new_table = AudioData()

        for row in self._data.values():
            if str(directory) in str(row.file.filename):
                new_table.add_row(row)

        return new_table

    def delete_row(self, file: str | Path | AudioFile) -> bool:
        """
        Remove a row from the table.
        Returns True if the row was found and deleted, False otherwise.
        """
        if isinstance(file, AudioFile):
            key = str(file.filename)
        else:
            key = str(file)

        if key in self._data:
            self.logger.debug(f"Deleting row from AudioData: {Path(key).name}")
            del self._data[key]
            return True
        return False

    def __len__(self) -> int:
        """Return the number of rows in the table."""
        return len(self._data)

    def __iter__(self) -> Iterator[AudioDataRow]:
        """Iterate over all rows in the table."""
        return iter(self._data.values())

    def __contains__(self, file: str | Path | AudioFile) -> bool:
        """Check if a file exists in the table."""
        if isinstance(file, AudioFile):
            file = str(file.filename)
        else:
            file = str(file)
        return str(file) in self._data
