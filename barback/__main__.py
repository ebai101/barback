import asyncio
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import cpu_count
from pathlib import Path
from typing import Iterable

import audio_file
import checks
import pandas as pd
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import (
    DataTable,
    DirectoryTree,
    Footer,
    Header,
    ProgressBar,
    Static,
)


class FileTable(DataTable):
    BINDINGS = [
        Binding("j", "cursor_down", "Cursor down", show=False),
        Binding("k", "cursor_up", "Cursor up", show=False),
    ]

    def add_df(self, df: pd.DataFrame):
        """Add DataFrame data to DataTable."""
        self.df = df
        self.add_columns(*self._add_df_columns())
        self.add_rows(self._add_df_rows()[0:])
        return self

    def update_df(self, df: pd.DataFrame):
        """Update DataFrameTable with a new DataFrame."""
        # Clear existing datatable
        self.clear(columns=True)
        # Redraw table with new dataframe
        self.add_df(df)

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


class Barback(App):
    BINDINGS = [
        Binding("q", "quit", "Quit", show=False, priority=True),
        Binding("x", "open_in_rx", "RX"),
        Binding("r", "open_in_reason", "Reason"),
        Binding("f", "open_in_finder", "Finder"),
        Binding("L", "check_loops", "Check Loops"),
        Binding("D", "find_duplicates", "Find Duplicates"),
        Binding("F", "final_check", "Final Check"),
    ]
    CSS_PATH = "barback.tcss"

    def __init__(self, audio_dir):
        super().__init__()
        self.executor = ProcessPoolExecutor(max_workers=cpu_count())
        self.audio_dir = Path(audio_dir)
        self.data = pd.DataFrame()
        self.loaded = False

    def action_check_loops(self) -> None:
        self.query_one("#info").update("Checking loops")
        self.check_loops()

    def action_open_in_rx(self) -> None:
        table = self.query_one("#table")
        selected_row = table.cursor_row
        af = table.get_row_at(selected_row)[0]
        self.query_one("#info").update(f"Opening {af.filename} in RX")
        subprocess.call(["open", "-a", "iZotope RX 10 Audio Editor", str(af.filename)])

    def action_open_in_reason(self) -> None:
        table = self.query_one("#table")
        selected_row = table.cursor_row
        af = table.get_row_at(selected_row)[0]
        self.query_one("#info").update(f"Opening {af.filename} in Reason")
        subprocess.call(
            [
                "/Applications/Keyboard Maestro.app/Contents/MacOS/keyboardmaestro",
                "D66BA3D1-E83A-4A96-878F-29DC4D7D8B85",
                "--parameter",
                f"{af.filename}",
            ]
        )

    def action_open_in_finder(self) -> None:
        table = self.query_one("#table")
        selected_row = table.cursor_row
        af = table.get_row_at(selected_row)[0]
        self.query_one("#info").update(f"Revealing {af.filename} in Finder")
        subprocess.call(
            [
                "/Applications/Keyboard Maestro.app/Contents/MacOS/keyboardmaestro",
                "B7271B0E-F479-434F-986A-C688A41E144A",
                "--parameter",
                f"{af.filename}",
            ]
        )

    def on_tree_node_highlighted(self, message: FileTree.NodeHighlighted) -> None:
        if not self.loaded:
            return
        table = self.query_one("#table")
        info = self.query_one("#info")

        info.update(f"Tree node {message.node.data.path} highlighted")
        if message.node.is_root:
            table.update_df(self.data)
        else:
            path = message.node.data.path
            info.update(f"Tree node {path} highlighted")
            subset = self.data[
                self.data.apply(
                    lambda row: str(path) in str(row["File"].filename), axis=1
                )
            ]
            table.update_df(subset)
        table.focus()

    @work
    async def check_loops(self):
        progress_bar = self.query_one("#progress")

        files = self.data["File"].tolist()
        tasks_remaining = len(files)
        progress_bar.update(total=tasks_remaining, progress=0)

        async def _proc(file):
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(self.executor, checks.check_loop, file)
            progress_bar.advance(1)
            return result

        tasks = [_proc(file) for file in files]
        results = await asyncio.gather(*tasks)

        self.data = pd.DataFrame(
            results, columns=["File", "Is Loop", "BPM", "#Bars", "ZC"]
        )
        self.query_one("#table").update_df(self.data)
        self.query_one("#info").update("Done checking loops")

    @work
    async def load_audio_files(self):
        info = self.query_one("#info")
        table = self.query_one("#table")
        progress_bar = self.query_one("#progress")

        valid_extensions = (".mp3", ".flac", ".wav", ".aif", ".aiff")
        if self.audio_dir.is_dir():
            files = [
                file.absolute()
                for file in self.audio_dir.rglob("*")
                if file.is_file() and file.suffix.lower() in valid_extensions
            ]
            if not files:
                info.update("No valid audio files found in the directory")
                return
        else:
            info.update("Must specify a valid directory")
            return

        tasks_remaining = len(files)
        info.update(f"Loading {len(files)} audio files from {self.audio_dir}")
        progress_bar.update(total=tasks_remaining, progress=0)

        async def _proc(file):
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self.executor, audio_file.AudioFile, file
            )
            progress_bar.advance(1)
            return result

        tasks = [_proc(file) for file in files]
        results = await asyncio.gather(*tasks)

        self.data = pd.DataFrame(results, columns=["File"])
        table.update_df(self.data)
        info.update(
            f"Finished loading {len(self.data)} audio files from {self.audio_dir}"
        )
        self.loaded = True

    def on_mount(self) -> None:
        table = self.query_one("#table")
        table.focus()
        table.cursor_type = "row"

        self.load_audio_files()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="info")
        yield ProgressBar(total=100, id="progress")
        yield Container(
            FileTable(id="table"),
            FileTree(self.audio_dir, id="tree"),
            id="main_container",
        )
        yield Footer()

    def on_unmount(self) -> None:
        self.executor.shutdown()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python script.py <audio_directory>")
        sys.exit(1)
    audio_dir = sys.argv[1]
    app = Barback(audio_dir)
    app.run()
