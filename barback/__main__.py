import sys

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.reactive import reactive
from textual.widgets import DataTable, Footer, Header, Static

import barback


class FileTable(DataTable):
    BINDINGS = [
        Binding("j", "cursor_down", "Cursor down", show=False),
        Binding("k", "cursor_up", "Cursor up", show=False),
        Binding("x", "open_in_rx", "Open in RX"),
        Binding("r", "open_in_reason", "Open in Reason"),
    ]

    def action_open_in_rx(self) -> None:
        selected_row = self.cursor_row
        if selected_row:
            self.app.open_in_rx(selected_row)

    def action_open_in_reason(self) -> None:
        selected_row = self.cursor_row
        if selected_row:
            self.app.open_in_reason(selected_row)


class MessageBox(Static):
    message = reactive("")

    def watch_message(self, message: str) -> None:
        self.update(message)

    def update_message(self, new_message: str) -> None:
        self.message = new_message


class Barback(App):
    BINDINGS = [
        Binding("q", "quit", "Quit", show=False, priority=True),
        Binding("L", "check_loops()", "Check Loops"),
    ]

    def __init__(self, audio_dir):
        super().__init__()
        self.audio_dir = audio_dir

    def open_in_rx(self, row: int) -> None:
        table = self.query_one(FileTable)
        message_box = self.query_one(MessageBox)
        message_box.update_message(f"Opening {table.get_row_at(row)[0]} in RX")

    def open_in_reason(self, row: int) -> None:
        table = self.query_one(FileTable)
        message_box = self.query_one(MessageBox)
        message_box.update_message(f"Opening {table.get_row_at(row)[0]} in Reason")

    def on_mount(self) -> None:
        message_box = self.query_one(MessageBox)

        table = self.query_one(DataTable)
        table.focus()
        table.cursor_type = "row"

        rows = barback.load_audio_files(self.audio_dir, message_box)
        if rows:
            table.add_columns(*rows[0])
            table.add_rows(rows[1:])
            message_box.update_message(
                f"Found {len(rows) - 1} audio files in {self.audio_dir}"
            )
        else:
            table.add_column("Message")
            table.add_row("No valid audio files found")

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(MessageBox(id="message_box"), FileTable(), id="main_container")
        yield Footer()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python script.py <audio_directory>")
        sys.exit(1)
    audio_dir = sys.argv[1]
    app = Barback(audio_dir)
    app.run()
