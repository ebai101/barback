from pathlib import Path
from typing import Iterable

import pandas as pd
from textual.binding import Binding
from textual.message import Message
from textual.widgets import DataTable, DirectoryTree, Static


class InfoBox(Static):
    class Info(Message):
        def __init__(self, text: str) -> None:
            self.text = text
            super().__init__()

    def __init__(self):
        super().__init__()


class DataFrameTable(DataTable):
    BINDINGS = [
        Binding("j", "cursor_down", "Cursor down", show=False),
        Binding("k", "cursor_up", "Cursor up", show=False),
    ]

    def __init__(self, id=""):
        super().__init__(id=id)
        self.selected_dir = None
        self.selected_mode = "files"
        self.mode_cols = ["File", "Duration", "Sample rate", "Bit depth"]

    def add_df(self, df: pd.DataFrame, sort_col: str = "File", sort_asc: bool = True):
        """Add DataFrame data to DataTable."""
        self.df = df
        if self.selected_dir:
            self.df = DataFrameTable.filter_df_by_dir(self.df, self.selected_dir)
        self.df = self.df.sort_values(sort_col, ascending=sort_asc)
        self.df = self.df.loc[:, self.mode_cols]
        self.add_columns(*self._add_df_columns())
        self.add_rows(self._add_df_rows()[0:])
        return self

    def update_df(
        self, df: pd.DataFrame, sort_col: str = "File", sort_asc: bool = True
    ):
        """Update DataFrameTable with a new DataFrame."""
        # Clear existing datatable
        self.clear(columns=True)
        # Redraw table with new dataframe
        self.add_df(df, sort_col=sort_col, sort_asc=sort_asc)

    @staticmethod
    def filter_df_by_dir(df: pd.DataFrame, dirname: str):
        return df[
            df.apply(
                lambda row: str(dirname) in str(row["File"].filename),
                axis=1,
            )
        ]

    def set_mode(self, mode: str):
        if mode in ["Files", "Loops", "Duplicates", "Finalizer", "Extender"]:
            self.selected_mode = mode
        else:
            raise ValueError(f"Mode {mode} is invalid")
        match self.selected_mode:
            case "Files":
                self.mode_cols = ["File", "Duration", "Sample rate", "Bit depth"]
            case "Loops":
                self.mode_cols = ["File", "Loop", "BPM", "Bars", "ZC"]
            case "Duplicates":
                self.mode_cols = ["File", "File 2", "Similarity"]

    def _add_df_rows(self) -> None:
        return self._get_df_rows()

    def _add_df_columns(self) -> None:
        return self._get_df_columns()

    def _get_df_rows(self) -> list[tuple]:
        """Convert dataframe rows to iterable."""
        return list(self.df.itertuples(index=False, name=None))

    def _get_df_columns(self) -> tuple:
        """Extract column names from dataframe."""
        return tuple(self.df.columns.values.tolist())


class FileTree(DirectoryTree):
    BINDINGS = [
        Binding("j", "cursor_down", "Cursor down", show=False),
        Binding("k", "cursor_up", "Cursor up", show=False),
    ]

    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        return [path for path in paths if path.is_dir()]
