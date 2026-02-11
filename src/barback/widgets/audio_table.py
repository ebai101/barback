from textual.binding import Binding
from textual.widgets import DataTable


class AudioTable(DataTable):
    BINDINGS = [
        Binding("j", "cursor_down", "Cursor down", show=False),
        Binding("k", "cursor_up", "Cursor up", show=False),
    ]

    def __init__(self, id: str = "", classes: str = "") -> None:
        super().__init__(id=id, classes=classes)
        self.cursor_type = "row"
