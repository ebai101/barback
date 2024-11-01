from dataclasses import fields
from typing import Any, Optional

from textual.binding import Binding
from textual.widgets import DataTable

from barback.audio_data import AudioData, AudioDataRow, SortDirection


class AudioTable(DataTable):  # type: ignore
    BINDINGS = [
        Binding("j", "cursor_down", "Cursor down", show=False),
        Binding("k", "cursor_up", "Cursor up", show=False),
    ]
    col_map = {
        "file": "File",
        "duration": "Duration",
        "sample_rate": "Sample rate",
        "bit_depth": "Bit depth",
        "loop": "Loop",
        "bpm": "BPM",
        "bars": "Bars",
        "zc": "ZC",
    }

    def __init__(self, id: str = "", classes: str = "") -> None:
        super().__init__(id=id, classes=classes)
        self.cursor_type = "row"
        self._current_columns: Optional[list[str]] = None
        self._current_sort_by: Optional[str] = None
        self._current_direction: SortDirection = "asc"
        self._row_data: dict[int, AudioDataRow] = {}

    def _get_display_name(self, internal_name: str) -> str:
        """Get display name for a column."""
        if internal_name in self.col_map:
            return self.col_map[internal_name]
        return internal_name

    def _get_internal_name(self, display_name: str) -> str:
        """Get internal name from display name."""
        reverse_map = {v: k for k, v in self.col_map.items()}
        if display_name in reverse_map:
            return reverse_map[display_name]
        return display_name

    def _get_sort_value(self, row: AudioDataRow, key: str) -> Any:
        """Get the value to sort by, handling None values."""
        value = getattr(row, key)
        return float("inf") if value is None else value

    def _expand_finalizer_issues(
        self,
        rows: list[AudioDataRow],
        display_columns: list[str],
        include_finalizer: bool,
    ) -> list[list[Any]]:
        """
        Expands rows with finalizer issues into multiple rows.
        Handles the special case when finalizer_issues is in display columns.
        """
        expanded_rows: list[list[Any]] = []

        for row in rows:
            if include_finalizer and (
                not row.finalizer_issues or len(row.finalizer_issues) == 0
            ):
                continue

            if include_finalizer:
                if row.finalizer_issues is None:
                    continue
                # Create a row for each finalizer issue
                for issue in row.finalizer_issues:
                    row_data: list[str] = []
                    for col in display_columns:
                        if col == "finalizer_issues":
                            row_data.append(issue.kind)
                            row_data.append(issue.message)
                        else:
                            row_data.append(getattr(row, col))
                    expanded_rows.append(row_data)
            else:
                # Normal row without finalizer expansion
                row_data = [getattr(row, col) for col in display_columns]
                expanded_rows.append(row_data)

        return expanded_rows

    def _process_duplicate_files(
        self, rows: list[list[Any]], file_col_idx: int
    ) -> list[list[Any]]:
        """
        After sorting, replaces duplicate filenames with empty strings.
        Keeps the first occurrence of each filename.
        """
        seen_files: set[str] = set()
        processed_rows: list[list[Any]] = []

        for row in rows:
            file_str = str(row[file_col_idx])
            if file_str in seen_files:
                # Replace filename with empty string
                new_row = row.copy()
                new_row[file_col_idx] = ""
                processed_rows.append(new_row)
            else:
                seen_files.add(file_str)
                processed_rows.append(row)

        return processed_rows

    def update_table(
        self,
        audio_data: AudioData,
        columns: Optional[list[str]] = None,
        sort_by: Optional[str] = None,
        direction: SortDirection = "asc",
    ) -> None:
        """
        Update the table with data from an AudioData instance.

        Args:
            audio_data: The AudioData instance to display
            columns: List of column names to include. If None, includes all columns
            sort_by: Column name to sort by
            direction: Sort direction ("asc" or "desc")
        """
        self._current_columns = columns
        self._current_sort_by = sort_by
        self._current_direction = direction

        # Clear existing data
        self.clear(columns=True)

        # Get all field names if columns not specified
        all_fields = [f.name for f in fields(AudioDataRow)]
        display_columns = columns if columns is not None else all_fields

        # Check if we need to handle finalizer issues
        include_finalizer = "finalizer_issues" in display_columns

        # Sort rows if needed
        if sort_by:
            sorted_rows = sorted(
                audio_data,
                key=lambda row: (
                    float("inf")
                    if getattr(row, sort_by) is None
                    else getattr(row, sort_by)
                ),
                reverse=(direction == "desc"),
            )
        else:
            sorted_rows = list(audio_data)

        # Expand rows with finalizer issues if needed
        expanded_rows = self._expand_finalizer_issues(
            sorted_rows, display_columns, include_finalizer
        )

        # Process duplicate filenames if showing finalizer issues
        if include_finalizer and len(expanded_rows) > 0:
            file_col_idx = display_columns.index("file")
            expanded_rows = self._process_duplicate_files(expanded_rows, file_col_idx)

        # Prepare headers
        if include_finalizer:
            # Remove finalizer_issues and add Kind and Issue columns
            display_columns = [
                col for col in display_columns if col != "finalizer_issues"
            ]
            header_names = []
            for col in display_columns:
                mapped_name = self.col_map.get(col, col) if col in self.col_map else col
                header_names.append(mapped_name)
            header_names.extend(["Kind", "Issue"])
        else:
            # Normal column headers
            header_names = [
                self.col_map.get(col, col) if col in self.col_map else col
                for col in display_columns
            ]

        # Add columns
        self.add_columns(*header_names)

        # Add rows to table
        for idx, row_data in enumerate(expanded_rows):
            formatted_row = ["" if value is None else str(value) for value in row_data]
            self.add_row(*formatted_row)

            # Store original data for reference
            if not include_finalizer:
                self._row_data[idx] = sorted_rows[idx]

    def refresh_table(self, audio_data: AudioData) -> None:
        """
        Refresh the table with new data from AudioData instance,
        maintaining current view settings.
        """
        self.update_table(
            audio_data,
            columns=self._current_columns,
            sort_by=self._current_sort_by,
            direction=self._current_direction,
        )

    def get_row_data(self, row_key: int) -> Optional[AudioDataRow]:
        """Get the AudioDataRow instance for a given row key."""
        return self._row_data.get(row_key)

    def get_cell_data(self, row_key: int, column_key: str) -> Any:
        """
        Get the original (non-string) value for a cell.

        Args:
            row_key: The row index
            column_key: The column name (display name)

        Returns:
            The original value from the AudioDataRow
        """
        row_data = self._row_data.get(row_key)
        if row_data is None:
            return None

        internal_name = self._get_internal_name(column_key)
        return getattr(row_data, internal_name)
