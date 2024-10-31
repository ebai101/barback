from typing import Any

import pandas as pd
from textual.binding import Binding
from textual.widgets import DataTable


class DataFrameTable(DataTable):  # type: ignore
    """A DataTable widget that displays a pandas DataFrame."""

    BINDINGS = [
        Binding("j", "cursor_down", "Cursor down", show=False),
        Binding("k", "cursor_up", "Cursor up", show=False),
    ]

    # Internal storage for DataFrame
    _current_df: pd.DataFrame
    _current_sort_col: str
    _current_sort_asc: bool

    def __init__(self, id: str = "") -> None:
        super().__init__(id=id)
        self.cursor_type = "row"
        self._current_df = pd.DataFrame()
        self._current_sort_col = "File"
        self._current_sort_asc = True

    def set_df(
        self,
        df: pd.DataFrame,
        sort_col: str | None = None,
        sort_asc: bool | None = None,
    ) -> None:
        """Set the DataFrame and optionally update sorting."""
        self._current_df = df

        if sort_col is not None:
            self._current_sort_col = sort_col
        if sort_asc is not None:
            self._current_sort_asc = sort_asc

        self._refresh_table()

    def _refresh_table(self) -> None:
        """Refresh the table display."""
        if not self._current_df.empty:
            if self._current_sort_col in self._current_df.columns:
                self._current_df = self._current_df.sort_values(
                    by=self._current_sort_col,
                    ascending=self._current_sort_asc,
                    na_position="last",
                )

            # Clear and rebuild the table
            self.clear(columns=True)
            self.add_columns(*self._get_df_columns())
            self.add_rows(self._get_df_rows(self._current_df))
        else:
            self.clear(columns=True)

    def _get_df_rows(self, df: pd.DataFrame) -> list[Any]:
        """Convert dataframe rows to iterable."""
        return list(df.itertuples(index=False, name=None))

    def _get_df_columns(self) -> tuple[Any]:
        """Extract column names from dataframe."""
        return tuple(self._current_df.columns.values.tolist())
