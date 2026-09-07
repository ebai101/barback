from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, OptionList, Static
from textual.widgets.option_list import Option


class FixTypeOptionList(OptionList):
    BINDINGS = (
        Binding("j", "cursor_down", "Cursor down", show=False),
        Binding("k", "cursor_up", "Cursor up", show=False),
    )


class IssueTypeSelectionDialog(ModalScreen[str | None]):
    """Generic dialog for selecting an issue type for various operations."""

    BINDINGS = (Binding("escape", "dismiss", "Cancel"),)

    def __init__(
        self,
        title: str,
        info: str,
        has_srbd: bool = False,
        has_silence: bool = False,
        has_zc: bool = False,
        has_loop: bool = False,
        has_key_sig: bool = False,
        action_prefix: str = "action",  # Used as prefix for the returned option ID
    ) -> None:
        """Initialize the issue type selection dialog.

        Args:
            title: Title text for the dialog
            info: Info text (e.g., "32 files with issues")
            has_srbd: Whether SR/BD issues are available
            has_zc: Whether ZC issues are available
            has_loop: Whether Loop issues are available
            action_prefix: Prefix for the returned action ID (e.g., "open", "fix")
        """
        super().__init__()
        self.title = title
        self.info = info
        self.has_srbd = has_srbd
        self.has_silence = has_silence
        self.has_zc = has_zc
        self.has_loop = has_loop
        self.has_key_sig = has_key_sig
        self.action_prefix = action_prefix

    def compose(self) -> ComposeResult:
        """Build the dialog UI."""
        with Vertical(id="fix_dialog"):
            yield Static(f"{self.title}", id="fix_dialog_title")
            yield Static(f"{self.info}", id="fix_dialog_info")

            options_list = FixTypeOptionList(id="fix_options")
            if self.has_srbd:
                options_list.add_option(
                    Option("SR/BD", id=f"{self.action_prefix}_srbd")
                )
            if self.has_silence:
                options_list.add_option(
                    Option("Silence", id=f"{self.action_prefix}_silence")
                )
            if self.has_zc:
                options_list.add_option(
                    Option("ZC (Zero Crossing)", id=f"{self.action_prefix}_zc")
                )
            if self.has_loop:
                options_list.add_option(Option("Loop", id=f"{self.action_prefix}_loop"))
            if self.has_key_sig:
                options_list.add_option(
                    Option("Key sig", id=f"{self.action_prefix}_key_sig")
                )

            yield options_list
            yield Footer()

    def on_mount(self) -> None:
        """Focus the options list and highlight the first option when mounted."""
        options = self.query_one("#fix_options", OptionList)
        if options.option_count > 0:
            options.highlighted = 0
        options.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle option selection."""
        self.dismiss(event.option.id)


class FixTypeDialog(IssueTypeSelectionDialog):
    """Dialog for selecting which fix type to apply."""

    BINDINGS = (Binding("escape", "dismiss", "Cancel"),)

    def __init__(
        self,
        filename: str | None = None,
        is_all: bool = False,
        file_count: int = 1,
        **kwargs,
    ) -> None:
        title = "Select Repair Type" if is_all else f"Fix {filename}"
        info = f"{file_count} file{'s' if file_count != 1 else ''} selected"
        super().__init__(title=title, info=info, action_prefix="fix", **kwargs)

    def compose(self) -> ComposeResult:
        """Override to add 'Apply All Fixes' option."""
        for widget in super().compose():
            if isinstance(widget, Vertical):
                for child in widget.children:
                    if isinstance(child, OptionList) and child.id == "fix_options":
                        yield child
                        child.add_option(Option("Apply All Fixes", id="fix_all"))
                    else:
                        yield child
            else:
                yield widget

    def on_mount(self) -> None:
        """Focus the options list and highlight the first option when mounted."""
        options = self.query_one("#fix_options", OptionList)
        options.highlighted = 0
        options.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle option selection."""
        self.dismiss(event.option.id)
