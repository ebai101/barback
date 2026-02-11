from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class FixTypeDialog(ModalScreen[str | None]):
    """Dialog for selecting which fix type to apply."""

    DEFAULT_CSS = """
    FixTypeDialog {
        align: center middle;
    }
    
    #dialog {
        width: 60;
        height: auto;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    
    #title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    
    #description {
        text-align: center;
        color: $text-muted;
        margin-bottom: 1;
    }
    
    #buttons {
        layout: horizontal;
        height: auto;
        align: center middle;
        margin-top: 1;
    }
    
    Button {
        margin: 0 1;
    }
    """

    def __init__(self, filename: str | None = None, is_all: bool = False) -> None:
        super().__init__()
        self.filename = filename
        self.is_all = is_all

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            if self.is_all:
                yield Static("Select Fix Type (All Files)", id="title")
                yield Static(
                    "Choose which fixes to apply to all files", id="description"
                )
            else:
                title = (
                    f"Select Fix Type: {self.filename}"
                    if self.filename
                    else "Select Fix Type"
                )
                yield Static(title, id="title")
                yield Static("Choose which fixes to apply", id="description")

            with Vertical(id="buttons"):
                yield Button("Fix SRBD", id="fix_srbd", variant="primary")
                yield Button("Apply Microfades", id="fix_microfades", variant="primary")
                yield Button("Apply All Fixes", id="fix_all", variant="success")
                yield Button("Cancel", id="cancel", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "cancel":
            self.dismiss(None)
        else:
            self.dismiss(event.button.id)
