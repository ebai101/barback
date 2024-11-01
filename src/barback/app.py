import os
import subprocess
from datetime import datetime
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Button, Footer, Header, ProgressBar, Rule

from barback.state import BarbackState, Mode
from barback.util.messages import (
    FileChanged,
    ProgressBarAdvance,
    ProgressBarUpdate,
    TableUpdate,
)
from barback.widgets.audio_table import AudioTable
from barback.widgets.file_tree import FileTree
from barback.widgets.info_box import InfoBox
from barback.workers.check_loops import check_loops
from barback.workers.file_watcher import watch_files
from barback.workers.finalizer import finalizer
from barback.workers.find_duplicates import find_duplicates
from barback.workers.init_audio_data import init_audio_data


class Barback(App):  # type: ignore
    BINDINGS = [
        Binding("q", "quit", "Quit", show=False, priority=True),
        Binding("x", "open_in_rx", "RX"),
        Binding("X", "open_all_issue_type_in_rx", "RX (All Issue Type)"),
        Binding("r", "open_in_reason", "Reason"),
        Binding("f", "open_in_finder", "Finder"),
        Binding("L", "check_loops", "Check Loops"),
        Binding("D", "find_duplicates", "Find Duplicates"),
        Binding("F", "finalizer", "Run Finalizer"),
    ]
    CSS_PATH = "barback.tcss"

    def __init__(self, audio_dir: str) -> None:
        super().__init__()
        self.state = BarbackState(
            audio_dir=Path(audio_dir),
            selected_dir=Path(audio_dir),
        )

    def action_check_loops(self) -> None:
        check_loops(self, self.state)

    def action_find_duplicates(self) -> None:
        find_duplicates(self, self.state)

    def action_finalizer(self) -> None:
        finalizer(self, self.state)

    def action_open_in_rx(self) -> None:
        table: AudioTable = self.query_one("#table", AudioTable)
        filename = table.get_cell_data(table.cursor_row, "file").filename
        self.info(f"Opening {os.path.basename(filename)} in RX")
        subprocess.call(["open", "-a", "iZotope RX 10 Audio Editor", str(filename)])

    def action_open_all_issue_type_in_rx(self) -> None:
        return
        if self.state.mode != Mode.FINALIZER:
            return
        table: AudioTable = self.query_one("#table", AudioTable)
        row = table.get_df_row_at(table.cursor_row)
        issue_kind = row["Issue Kind"]

        df = table.get_df()
        file_paths = df[df["Issue Kind"] == issue_kind]["Full Path"].tolist()
        if len(file_paths) > 32:
            old_len = len(file_paths)
            file_paths = file_paths[:32]
            self.info(f"Opening first 32 {issue_kind} issues in RX ({old_len} total)")
        else:
            self.info(f"Opening all {issue_kind} issues in RX")
        subprocess.call(["open", "-a", "iZotope RX 10 Audio Editor"] + file_paths)

    def action_open_in_reason(self) -> None:
        table: AudioTable = self.query_one("#table", AudioTable)
        filename = table.get_cell_data(table.cursor_row, "file").filename
        self.info(f"Opening {os.path.basename(filename)} in Reason")
        subprocess.call(
            [
                "/Applications/Keyboard Maestro.app/Contents/MacOS/keyboardmaestro",
                "D66BA3D1-E83A-4A96-878F-29DC4D7D8B85",
                "--parameter",
                f"{filename}",
            ]
        )

    def action_open_in_finder(self) -> None:
        table: AudioTable = self.query_one("#table", AudioTable)
        filename = table.get_cell_data(table.cursor_row, "file").filename
        self.info(f"Revealing {os.path.basename(filename)} in Finder")
        subprocess.call(
            [
                "/Applications/Keyboard Maestro.app/Contents/MacOS/keyboardmaestro",
                "B7271B0E-F479-434F-986A-C688A41E144A",
                "--parameter",
                f"{filename}",
            ]
        )

    def on_tree_node_highlighted(self, message: FileTree.NodeHighlighted) -> None:  # type: ignore
        print(f"tree_node_highlighted {message}")
        table = self.query_one("#table", AudioTable)
        if message.node.is_root:
            self.state.selected_dir = self.state.audio_dir
        elif message.node.data is not None:
            self.state.selected_dir = message.node.data.path
        else:
            self.state.selected_dir = self.state.audio_dir
        if self.state.loaded:
            self.post_message(TableUpdate("on_tree_node_highlighted"))
            table.focus()

    def on_button_pressed(self, message: Button.Pressed) -> None:
        print(f"button_pressed {message}")
        match message.button.id:
            case "files-button":
                self.state.mode = Mode.FILES
            case "loops-button":
                self.state.mode = Mode.LOOPS
            case "duplicates-button":
                self.state.mode = Mode.DUPLICATES
            case "finalizer-button":
                self.state.mode = Mode.FINALIZER
            case "extender-button":
                self.state.mode = Mode.EXTENDER
            case _:
                raise ValueError(f"Unexpected button press: #{message.button.id}")
        self.post_message(TableUpdate("on_button_pressed"))

    def on_progress_bar_update(self, message: ProgressBarUpdate) -> None:
        print(f"progress_bar_update {message}")
        progress_bar = self.query_one("#progress", ProgressBar)
        progress_bar.update(total=message.total, progress=message.progress)

    def on_progress_bar_advance(self, message: ProgressBarAdvance) -> None:
        progress_bar = self.query_one("#progress", ProgressBar)
        progress_bar.advance(message.amount)

    def on_table_update(self, message: TableUpdate) -> None:
        print(f"table_update {message}")
        if not self.state.loaded:
            return

        table = self.query_one("#table", AudioTable)
        current_mode = self.state.mode
        current_dir = self.state.selected_dir

        if current_dir == self.state.audio_dir:
            filtered_data = self.state.audio_data
        else:
            filtered_data = self.state.audio_data.filter_by_dir(self.state.selected_dir)

        match current_mode:
            case Mode.FILES:
                table.update_table(
                    filtered_data,
                    columns=["file", "duration", "sample_rate", "bit_depth"],
                    sort_by="file",
                    direction="asc",
                )
            case Mode.LOOPS:
                table.update_table(
                    filtered_data,
                    columns=["file", "loop", "bpm", "bars", "zc"],
                    sort_by="file",
                    direction="asc",
                )
            case Mode.DUPLICATES:
                pass
            case Mode.FINALIZER:
                table.update_table(
                    filtered_data,
                    columns=["file", "finalizer_issues"],
                    sort_by="file",
                    direction="asc",
                )

            case Mode.EXTENDER:
                pass
        table.focus()

    def on_file_changed(self, message: FileChanged) -> None:
        print(message)
        self.info(
            f"{message.path.name} was {message.change_type} on disk at {datetime.now().strftime('%H:%M:%S')}"
        )
        # refresh_file(self, self.state, message.path)

    def info(self, text: str) -> None:
        print(text)
        info_box = self.query_one("#info", InfoBox)
        info_box.update(text)

    def on_mount(self) -> None:
        init_audio_data(self, self.state)
        watch_files(self, self.state)

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            InfoBox(id="info"),
            Container(
                Button("Files", id="files-button", classes="mode-button"),
                Button("Loops", id="loops-button", classes="mode-button"),
                Button("Duplicates", id="duplicates-button", classes="mode-button"),
                Button("Finalizer", id="finalizer-button", classes="mode-button"),
                Button("Extender", id="extender-button", classes="mode-button"),
                id="mode-switcher",
            ),
            ProgressBar(total=100, id="progress"),
            id="head",
        )
        yield Rule(line_style="ascii", id="rule")
        yield Container(
            AudioTable(id="table"),
            FileTree(self.state.audio_dir, id="tree"),
            id="body",
        )
        yield Footer()

    def on_unmount(self) -> None:
        self.state.executor.shutdown()
        self.workers.cancel_all()
