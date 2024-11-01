from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Iterator, Literal, Optional, Union

from barback.audio_file import AudioFile
from barback.util.types import FinalizerIssue

# Type definitions
SortDirection = Literal["asc", "desc"]


@dataclass
class AudioDataRow:
    file: AudioFile
    duration: Optional[float] = None
    sample_rate: Optional[float] = None
    bit_depth: Optional[str] = None
    loop: Optional[str] = None
    bpm: Optional[int] = None
    bars: Optional[int] = None
    zc: Optional[str] = None
    finalizer_issues: Optional[list[FinalizerIssue]] = None


class AudioData:
    def __init__(self) -> None:
        self._data: dict[str, AudioDataRow] = {}

    def add_row(self, row: AudioDataRow) -> None:
        """Add a new row to the table."""
        self._data[str(row.file.filename)] = row

    def get_row(self, file_path: Union[str, Path, AudioFile]) -> Optional[AudioDataRow]:
        """Get a row by file path."""
        return self._data.get(str(file_path))

    def get_files(self) -> list[AudioFile]:
        """Gets all the AudioFiles in the table."""
        return self.get_col("file")

    def get_col(self, column: str) -> list[Any]:
        """Get values from the specified column for all rows."""
        valid_fields = {f.name for f in fields(AudioDataRow)}
        if column not in valid_fields:
            raise ValueError(
                f"Invalid column name: {column}. Valid columns are: {valid_fields}"
            )

        return [getattr(row, column) for row in self._data.values()]

    def update_row(self, file_path: Union[str, Path, AudioFile], **kwargs: Any) -> bool:
        """
        Update an existing row with new values.
        Returns True if the row was found and updated, False otherwise.
        """
        key = str(file_path)
        if key in self._data:
            row = self._data[key]
            valid_fields = {f.name for f in fields(AudioDataRow)}
            for attr, value in kwargs.items():
                if attr in valid_fields:
                    setattr(row, attr, value)
            return True
        return False

    def filter_by_dir(self, directory: Union[str, Path]) -> "AudioData":
        """Return a new table containing only rows where the file is in the specified directory."""
        directory = Path(directory).resolve()
        new_table = AudioData()

        for row in self._data.values():
            if str(directory) in str(row.file.filename):
                new_table.add_row(row)

        return new_table

    def _get_sort_value(self, row: AudioDataRow, key: str) -> Any:
        """Get the value to sort by, handling None values."""
        value = getattr(row, key)
        # Place None values at the end for ascending, start for descending
        if value is None:
            return float("inf")
        return value

    def _get_sort_key(
        self,
        sort_by: Union[str, list[str]],
        direction: Union[SortDirection, list[SortDirection]],
    ) -> Any:
        """
        Create a sort key function that sorts by multiple columns in order.
        Each subsequent sort preserves the order of equal elements from previous sorts.
        """
        # Convert to lists for consistent handling
        sort_keys = [sort_by] if isinstance(sort_by, str) else sort_by
        directions = [direction] if isinstance(direction, str) else direction

        if len(directions) == 1:
            directions = directions * len(sort_keys)

        def key_func(row: AudioDataRow) -> Any:
            return tuple(
                (1 if d == "desc" else -1) * self._get_sort_value(row, k)
                for k, d in zip(sort_keys, directions)
            )

        return key_func

    def __len__(self) -> int:
        """Return the number of rows in the table."""
        return len(self._data)

    def __iter__(self) -> Iterator[AudioDataRow]:
        """Iterate over all rows in the table."""
        return iter(self._data.values())

    def __contains__(self, file_path: Union[str, Path, AudioFile]) -> bool:
        """Check if a file exists in the table."""
        return str(file_path) in self._data
