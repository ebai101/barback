import asyncio
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import cpu_count
from pathlib import Path
from typing import Iterable

import audio_file
import pandas as pd
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import DirectoryTree, Footer, Header, ProgressBar, Static
from textual_pandas.widgets import DataFrameTable

import barback


class FileTable(DataFrameTable):
    BINDINGS = [
        Binding("j", "cursor_down", "Cursor down", show=False),
        Binding("k", "cursor_up", "Cursor up", show=False),
    ]


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
        Binding("x", "open_in_rx", "Open in RX"),
        Binding("r", "open_in_reason", "Open in Reason"),
        Binding("L", "check_loops", "Check Loops"),
        Binding("D", "find_duplicates", "Find Duplicates"),
        Binding("F", "final_check", "Final Check"),
    ]
    CSS_PATH = "barback.tcss"

    def __init__(self, audio_dir):
        super().__init__()
        self.executor = ProcessPoolExecutor(max_workers=cpu_count())
        self.audio_dir = audio_dir
        self.data = pd.DataFrame(columns=["File", "Loop", "BPM", "Bars", "ZC"])
        self.loaded = False

    def action_check_loops(self) -> None:
        self.query_one("#message").update("Checking loops")
        self.check_loops()

    def action_open_in_rx(self) -> None:
        table = self.query_one("#table")
        selected_row = table.cursor_row
        if selected_row:
            self.query_one("#message").update(
                f"Opening {table.get_row_at(selected_row)[0]} in RX"
            )

    def action_open_in_reason(self) -> None:
        table = self.query_one("#table")
        selected_row = table.cursor_row
        if selected_row:
            self.query_one("#message").update(
                f"Opening {table.get_row_at(selected_row)[0]} in Reason"
            )

    def on_tree_node_highlighted(self, message: FileTree.NodeHighlighted) -> None:
        if self.loaded:
            self.query_one("#message").update(f"Tree node {message.node} highlighted")

    @work
    async def check_loops(self):
        progress_bar = self.query_one("#progress")

        files = self.data["File"].tolist()
        tasks_remaining = len(files)
        progress_bar.update(total=tasks_remaining, progress=0)

        async def _proc(file):
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(self.executor, barback.check_loop, file)
            progress_bar.advance(1)
            return result

        tasks = [_proc(file) for file in files]
        results = await asyncio.gather(*tasks)

        self.data = pd.DataFrame(
            results, columns=["File", "Is Loop", "BPM", "#Bars", "ZC"]
        )
        self.query_one("#table").update_df(self.data)
        self.query_one("#message").update("Done checking loops")

    @work
    async def load_audio_files(self):
        message = self.query_one("#message")
        table = self.query_one("#table")
        progress_bar = self.query_one("#progress")

        valid_extensions = (".mp3", ".flac", ".wav", ".aif", ".aiff")
        if os.path.isdir(self.audio_dir):
            files = [
                os.path.join(root, file)
                for root, _, files in os.walk(self.audio_dir)
                for file in files
                if file.lower().endswith(valid_extensions)
            ]
            if not files:
                message.update("No valid audio files found in the directory")
                return
        else:
            message.update("Must specify a valid directory")
            return

        tasks_remaining = len(files)
        message.update(f"Loading {len(files)} audio files from {self.audio_dir}")
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
        message.update(
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
        yield Static(id="message")
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
