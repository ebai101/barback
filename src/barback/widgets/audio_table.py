from dataclasses import fields
from typing import Any, Optional, Type, TypeVar, Union

from textual.binding import Binding
from textual.widgets import DataTable

from barback.audio_data import AudioData, AudioDataRow, SortDirection

ExpectType = TypeVar("ExpectType")


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
        self._table: dict[int, AudioDataRow] = {}

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

    @property
    def audio_data(self):
        return self._table.values()

    @staticmethod
    def _format_cell(data: Any) -> str:
        if data is None:
            return ""
        elif isinstance(data, float):
            return f"{data:.2f}"
        else:
            return str(data)

    def _process_finalizer_rows(
        self,
        audio_data_rows: list[AudioDataRow],
        display_columns: list[str],
    ) -> tuple[list[list[str]], list[AudioDataRow]]:
        """
        Expands rows with finalizer issues into multiple rows.
        Keeps only the first occurrence of each filename.
        """
        seen_files: set[str] = set()
        result_str: list[list[str]] = []
        result_adr: list[AudioDataRow] = []

        for ad_row in audio_data_rows:
            if not ad_row.finalizer_issues or len(ad_row.finalizer_issues) == 0:
                continue

            for issue in ad_row.finalizer_issues:
                # build row
                str_row: list[str] = []
                for col in display_columns:
                    if col == "finalizer_issues":
                        str_row.append(AudioTable._format_cell(issue.kind))
                        str_row.append(AudioTable._format_cell(issue.message))
                    else:
                        str_row.append(AudioTable._format_cell(getattr(ad_row, col)))

                # Don't show filename of duplicate rows
                file_str = str(ad_row.file)
                file_idx = display_columns.index("file")
                if file_str in seen_files:
                    str_row[file_idx] = "|"
                else:
                    seen_files.add(file_str)

                result_str.append(str_row)
                result_adr.append(ad_row)

        return result_str, result_adr

    def update_table(
        self,
        audio_data: AudioData,
        columns: Optional[list[str]] = None,
        sort_by: Optional[Union[str | list]] = None,
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
        self._table = {}

        # Get all field names if columns not specified
        all_fields = [f.name for f in fields(AudioDataRow)]
        display_columns = columns if columns is not None else all_fields

        # Sort rows if needed
        if sort_by is not None:

            def _key(obj, attr) -> Any:
                if "." in attr:
                    parts = attr.split(".")
                    value = obj
                    for part in parts:
                        value = getattr(value, part, None)
                    return float("inf") if value is None else value
                value = getattr(obj, attr, None)
                return float("inf") if value is None else value

            audio_data_rows = sorted(
                audio_data,
                key=lambda row: tuple(
                    [
                        _key(row, attr)
                        for attr in (
                            sort_by if isinstance(sort_by, list) else [sort_by]
                        )
                    ]
                ),
                reverse=(direction == "desc"),
            )
        else:
            audio_data_rows = list(audio_data)

        # Check if we need to handle finalizer issues
        include_finalizer = "finalizer_issues" in display_columns

        # Process AudioDataRows into lists of strings
        rows: list[str] = []
        if include_finalizer:
            # Expand rows and process duplicate files
            rows, audio_data_rows = self._process_finalizer_rows(
                audio_data_rows, display_columns
            )
        else:
            # Normal rows
            rows = [
                [AudioTable._format_cell(getattr(row, col)) for col in display_columns]
                for row in audio_data_rows
            ]

        if include_finalizer:
            display_columns.remove("finalizer_issues")

        # Remap names
        header_names = [
            self.col_map.get(col, col) if col in self.col_map else col
            for col in display_columns
        ]

        if include_finalizer:
            header_names.extend(["Kind", "Issue"])

        # Add columns
        self.clear(columns=True)
        for col in header_names:
            self.add_column(col, key=col)

        for idx, row in enumerate(rows):
            formatted_row = ["" if value is None else value for value in row]
            self.add_row(*formatted_row)
            self._table[idx] = audio_data_rows[idx]

    def get_cell_data(
        self,
        row_key: int,
        column_key: str,
        expect_type: Type[ExpectType],
    ) -> ExpectType:
        """
        Get the original (non-string) value for a cell.

        Args:
            row_key: The row index
            column_key: The column name (display name)

        Returns:
            The original value from the AudioDataRow
        """
        row_data = self._table.get(row_key)
        if row_data is None:
            raise KeyError(f"Row key {row_key} not in table")

        internal_name = self._get_internal_name(column_key)
        val = getattr(row_data, internal_name)
        if isinstance(val, expect_type):
            return val
        return expect_type(val)

    def get_display_data(self, row_key: int, column_key: str) -> str:
        """
        Get the actual displayed value of a cell .

        Args:
            row_key (int): The row index
            column_key (str): The column name (display name)

        Returns:
            The displayed value in the table
        """

        col = list(self.get_column(column_key))
        return col[row_key]
