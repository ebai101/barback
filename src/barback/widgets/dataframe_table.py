from typing import Any

import pandas as pd
from textual.binding import Binding
from textual.widgets import DataTable


class DataFrameTable(DataTable):  # type: ignore

    BINDINGS = [
        Binding("j", "cursor_down", "Cursor down", show=False),
        Binding("k", "cursor_up", "Cursor up", show=False),
    ]

    _display_df: pd.DataFrame
    _current_df: pd.DataFrame
    _current_cols: list[str]
    _current_sort_col: str | list[str]
    _current_sort_asc: bool

    def __init__(self, id: str = "") -> None:
        super().__init__(id=id)
        self.cursor_type = "row"
        self._display_df = pd.DataFrame()
        self._current_df = pd.DataFrame()
        self._current_cols = []
        self._current_sort_col = "File"
        self._current_sort_asc = True

    def set_df(
        self,
        df: pd.DataFrame,
        columns: list[str] | None = None,
        sort_col: str | list[str] | None = None,
        sort_asc: bool | None = None,
    ) -> None:
        self._current_df = df

        if columns is not None:
            self._current_cols = columns
        else:
            self._current_cols = []

        if sort_col is not None:
            self._current_sort_col = sort_col
        if sort_asc is not None:
            self._current_sort_asc = sort_asc

        self._refresh_table()

    def get_df(self) -> pd.DataFrame:
        return self._current_df

    def get_df_row_at(self, index: int) -> pd.Series:
        if not self._current_df.empty and 0 <= index < len(self._current_df):
            return self._current_df.iloc[index]
        raise IndexError(f"Row index {index} out of bounds")

    def _refresh_table(self) -> None:
        if not self._current_df.empty:
            if isinstance(self._current_sort_col, str):
                has_cols = self._current_sort_col in self._current_df.columns
            else:
                has_cols = all(
                    col in self._current_df.columns for col in self._current_sort_col
                )
            if has_cols:
                self._current_df = self._current_df.sort_values(
                    by=self._current_sort_col,
                    ascending=self._current_sort_asc,
                    na_position="last",
                )
            if self._current_cols != []:
                self._display_df = self._current_df.loc[:, self._current_cols]
            else:
                self._display_df = self._current_df

            self.clear(columns=True)
            self.add_columns(*self._get_df_columns())
            self.add_rows(self._get_df_rows(self._display_df))
        else:
            self.clear(columns=True)

    def _get_df_rows(self, df: pd.DataFrame) -> list[Any]:
        return list(df.itertuples(index=False, name=None))

    def _get_df_columns(self) -> tuple[Any]:
        return tuple(self._display_df.columns.values.tolist())
