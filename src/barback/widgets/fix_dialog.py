from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, OptionList, Static
from textual.widgets.option_list import Option


class FixTypeOptionList(OptionList):
    BINDINGS = [
        Binding("j", "cursor_down", "Cursor down", show=False),
        Binding("k", "cursor_up", "Cursor up", show=False),
    ]


class FixTypeDialog(ModalScreen[str | None]):
    """Dialog for selecting which fix type to apply."""

    BINDINGS = [Binding("escape", "dismiss", "Cancel")]

    def __init__(
        self,
        filename: str | None = None,
        is_all: bool = False,
        file_count: int = 1,
        has_srbd: bool = False,
        has_zc: bool = False,
        has_loop: bool = False,
    ) -> None:
        """
        Initialize the fix type dialog.

        Args:
            filename: Name of the file (for single file mode)
            is_all: Whether this is for fixing all files
            file_count: Number of files that will be fixed
            has_srbd: Whether the file(s) have SR/BD issues
        """
        super().__init__()
        self.filename = filename
        self.is_all = is_all
        self.file_count = file_count
        self.has_srbd = has_srbd
        self.has_zc = has_zc
        self.has_loop = has_loop

    def compose(self) -> ComposeResult:
        """Build the dialog UI."""
        with Vertical(id="fix_dialog"):
            if self.is_all:
                yield Static("Select Fix Type", id="fix_dialog_title")
            else:
                yield Static(f"Fix: {self.filename}", id="fix_dialog_title")

            if self.file_count == 1:
                yield Static("1 file selected", id="fix_dialog_info")
            else:
                yield Static(f"{self.file_count} files selected", id="fix_dialog_info")

            options_list = FixTypeOptionList(id="fix_options")
            if self.has_srbd:
                options_list.add_option(Option("Fix SR/BD", id="fix_srbd"))
            if self.has_zc:
                options_list.add_option(Option("Fix ZC (Microfades)", id="fix_zc"))
            if self.has_loop:
                options_list.add_option(Option("Fix Loop", id="fix_loop"))
            options_list.add_option(Option("Apply All Fixes", id="fix_all"))

            yield options_list
            yield Footer()

    def on_mount(self) -> None:
        """Focus the options list and highlight the first option when mounted."""
        options = self.query_one("#fix_options", OptionList)
        options.highlighted = 0
        options.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle option selection."""
        self.dismiss(event.option.id)
