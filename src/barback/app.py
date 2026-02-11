import subprocess
from collections.abc import Generator
from pathlib import Path
from typing import Any

from textual.app import App
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Footer, Header, Input, ProgressBar, Rule, Static

from barback.audio_processor import AudioProcessor
from barback.state import BarbackState
from barback.util.logger import get_logger
from barback.util.messages import (
    BarbackLoaded,
    ProgressBarAdvance,
    ProgressBarUpdate,
    TableUpdate,
)
from barback.validation import summarize_issues
from barback.widgets.audio_table import AudioTable
from barback.widgets.fix_dialog import FixTypeDialog
from barback.workers.audio_fixer import (
    fix_all_issues_all_files,
    fix_all_issues_selected_file,
    fix_srbd_all_files,
    fix_srbd_selected_file,
    fix_zc_all_files,
    fix_zc_selected_file,
)
from barback.workers.file_processor import init_audio_data
from barback.workers.file_watcher import watch_files


class Barback(App):
    CSS_PATH = "barback.tcss"
    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("a", "toggle_show_all", "Toggle All/Issues"),
        Binding("x", "open_in_rx", "RX"),
        Binding("X", "open_all_issue_type_in_rx", "RX (All Issue Type)"),
        Binding("m", "open_in_myriad", "Myriad"),
        Binding("M", "open_all_issue_type_in_myriad", "Myriad (All Issue Type)"),
        Binding("r", "fix_selected", "Fix"),
        Binding("R", "fix_all_issues", "Fix All"),
        Binding("f", "reveal_in_finder", "Finder"),
        Binding("/", "enter_search_mode", "Search", show=False),
        Binding("escape", "exit_search_mode", "Exit Search", show=False),
    ]

    def __init__(self, audio_dir: str) -> None:
        super().__init__()
        self.state = BarbackState(
            audio_dir=Path(audio_dir),
            selected_dir=Path(audio_dir),
        )
        self.audio_processor = AudioProcessor()
        self.logger = get_logger()
        self.logger.info(f"Barback initialized with directory: {audio_dir}")

    def compose(self) -> Generator[Any, Any, None]:
        """Build the UI layout."""
        yield Header()
        yield Container(
            Static(id="info"),
            Static(),
            Static(id="stats"),
            Static(),
            ProgressBar(total=100, id="progress"),
            id="head",
        )
        yield Rule(line_style="ascii", id="rule")
        yield Container(
            AudioTable(id="table"),
            id="body",
        )
        yield Input(id="search", classes="hidden")
        yield Footer()

    def on_mount(self) -> None:
        """Called when app mounts - kick off the workers."""
        self.theme = "tokyo-night"
        self.info("Starting Barback...")

        # Start the initial scan
        init_audio_data(self, self.state)

    def info(self, text: str) -> None:
        """Update the info box with status messages."""
        info_box = self.query_one("#info", Static)
        info_box.update(text)
        self.logger.info(text)

    def update_stats(self, text: str) -> None:
        """Update the stats line with file counts."""
        stats_box = self.query_one("#stats", Static)
        stats_box.update(text)

    # -------------------------------------------------------------------------
    # Message Handlers
    # -------------------------------------------------------------------------

    def on_barback_loaded(self, message: BarbackLoaded) -> None:
        """Called when initial scan completes."""
        self.state.loaded = True

        # Hide progress bar
        progress = self.query_one("#progress", ProgressBar)
        progress.display = False

        # Start file watcher now that initial load is done
        watch_files(self, self.state)

        self.info(f"Watching {self.state.audio_dir} for changes")

    def on_table_update(self, message: TableUpdate) -> None:
        """Refresh the table whenever data changes."""
        self._refresh_table()

    def on_progress_bar_update(self, message: ProgressBarUpdate) -> None:
        """Update progress bar total and current value."""
        progress = self.query_one("#progress", ProgressBar)
        progress.display = True
        progress.update(total=message.total, progress=message.progress)

    def on_progress_bar_advance(self, message: ProgressBarAdvance) -> None:
        """Advance progress bar by a given amount."""
        progress = self.query_one("#progress", ProgressBar)
        progress.advance(message.amount)

    def on_data_table_header_selected(self, event: AudioTable.HeaderSelected) -> None:
        """Sort table by the selected column."""
        table = event.data_table
        table.sort(event.column_key)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes."""
        if event.input.id == "search":
            self.state.search_query = event.value.lower()
            self._refresh_table()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in search - return focus to table."""
        if event.input.id == "search":
            table = self.query_one("#table", AudioTable)
            table.focus()
            self.info(f"Search: {self.state.search_query or '(empty)'}")

    # -------------------------------------------------------------------------
    # Table Management
    # -------------------------------------------------------------------------

    def _refresh_table(self) -> None:
        """
        Rebuild the table from state.audio_data.

        Shows only files with issues for a cleaner view.
        If you want to show all files, remove the filter.
        """
        table = self.query_one("#table", AudioTable)

        # Save current cursor position before clearing
        old_cursor_row = table.cursor_row if table.row_count > 0 else 0

        # Clear existing rows
        table.clear()

        # Define columns
        if not table.columns:
            table.add_column("Filename", key="filename")
            table.add_column("Duration", key="duration")
            table.add_column("SR", key="sample_rate")
            table.add_column("BD", key="bit_depth")
            table.add_column("Loop", key="loop")
            table.add_column("BPM", key="bpm")
            table.add_column("Bars", key="bars")
            table.add_column("ZC", key="zc")
            table.add_column("Issues", key="issues")

        # Filter to selected directory if needed
        filtered_data = self.state.audio_data.filter_by_dir(self.state.selected_dir)

        if self.state.show_all_files:
            rows_to_display = list(filtered_data)
        else:
            rows_to_display = [row for row in filtered_data if row.issues]

        # Apply search filter if in search mode
        if self.state.search_mode and self.state.search_query:
            rows_to_display = [
                row
                for row in rows_to_display
                if self.state.search_query in row.file.filename.name.lower()
            ]

        # Populate table
        for row in rows_to_display:
            # Format issue summary
            if row.issues:
                issue_summary = summarize_issues(row.issues)
            else:
                issue_summary = "—"

            # Highlight search query in filename if searching
            filename_display = row.file.filename.name
            if self.state.search_mode and self.state.search_query:
                filename_display = self._highlight_search(
                    filename_display, self.state.search_query
                )

            # Add row to table
            table.add_row(
                filename_display,
                f"{row.duration:.2f}s" if row.duration else "—",
                str(int(row.sample_rate)) if row.sample_rate else "—",
                row.bit_depth or "—",
                row.loop or "—",
                str(row.bpm) if row.bpm else "—",
                str(row.bars) if row.bars else "—",
                row.zc or "—",
                issue_summary,
                key=str(row.file.filename),  # Use full path as key for updates
            )

        # Restore cursor position, adjusting if needed
        if table.row_count > 0:
            # If the old position is beyond the new row count, move to the last row
            new_cursor_row = min(old_cursor_row, table.row_count - 1)
            table.move_cursor(row=new_cursor_row)

        # Update stats line (separate from info messages)
        total_files = len(self.state.audio_data)
        files_with_issues = sum(1 for row in self.state.audio_data if row.issues)

        if self.state.loaded:
            if self.state.search_mode:
                self.update_stats(
                    f"{len(rows_to_display)} matching files "
                    f"(of {total_files} total, {files_with_issues} with issues)"
                )
            else:
                self.update_stats(
                    f"{total_files} files scanned, {files_with_issues} with issues"
                )

    def _highlight_search(self, text: str, query: str) -> str:
        """Highlight search query in text using Rich markup."""
        if not query:
            return text

        # Case-insensitive search but preserve original case
        lower_text = text.lower()
        start_idx = lower_text.find(query)

        if start_idx == -1:
            return text

        # Build highlighted string
        before = text[:start_idx]
        match = text[start_idx : start_idx + len(query)]
        after = text[start_idx + len(query) :]

        return f"{before}[bold yellow on blue]{match}[/]{after}"

    def _get_selected_file_path(self) -> Path | None:
        """Get the file path of the currently selected row."""
        table = self.query_one("#table", AudioTable)

        if table.row_count == 0:
            return None

        try:
            # Get the filename from the first column of the current row
            filename_display = table.get_cell_at((table.cursor_row, 0))

            # Strip Rich markup if present (from search highlighting)
            # Extract just the filename by removing markup tags
            import re

            filename = re.sub(r"\[.*?\]", "", filename_display)

            # Search through audio_data to find the matching file by name
            for row in self.state.audio_data:
                if row.file.filename.name == filename:
                    return row.file.filename  # This is the full Path object

        except Exception as e:
            self.info(f"Error getting file path: {e}")

        return None

    def _get_current_issue_kind(self) -> str | None:
        """Get the issue kind from the currently selected row."""
        file_path = self._get_selected_file_path()
        if not file_path:
            return None

        row = self.state.audio_data.get_row(file_path)
        if row and row.issues:
            # Return the kind of the first issue
            return row.issues[0].kind

        return None

    def _get_files_with_issue_kind(self, issue_kind: str) -> list[Path]:
        """Get all files that have issues of the specified kind."""
        files = []
        for row in self.state.audio_data:
            if row.issues:
                if any(issue.kind == issue_kind for issue in row.issues):
                    if self.state.search_mode and self.state.search_query:
                        if self.state.search_query in row.file.filename.name.lower():
                            files.append(row.file.filename)
                    else:
                        files.append(row.file.filename)
        return files

    # -------------------------------------------------------------------------
    # Actions - Basic Navigation
    # -------------------------------------------------------------------------

    def action_cursor_down(self) -> None:
        """Move cursor down in table."""
        if self.state.search_mode:
            return  # Don't move cursor while typing
        table = self.query_one("#table", AudioTable)
        table.action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move cursor up in table."""
        if self.state.search_mode:
            return  # Don't move cursor while typing
        table = self.query_one("#table", AudioTable)
        table.action_cursor_up()

    def action_toggle_show_all(self) -> None:
        """Toggle between showing all files and only files with issues."""
        self.state.show_all_files = not self.state.show_all_files
        self.logger.debug(f"Toggled show all files: {self.state.show_all_files}")
        self._refresh_table()

        if self.state.show_all_files:
            self.info("Showing all files")
        else:
            self.info("Showing only files with issues")

    def action_enter_search_mode(self) -> None:
        """Enter search mode."""
        self.logger.debug("Entered search mode")
        self.state.search_mode = True
        self.state.search_query = ""

        # Show and focus the search input
        search_input = self.query_one("#search", Input)
        search_input.value = ""
        search_input.focus()

        self.info("Search mode (ESC to exit)")

    def action_exit_search_mode(self) -> None:
        """Exit search mode and clear search."""
        self.logger.debug(f"Exited search mode (query was: '{self.state.searchquery}')")
        if not self.state.search_mode:
            return

        self.state.search_mode = False
        self.state.search_query = ""

        # Refocus the table
        table = self.query_one("#table", AudioTable)
        table.focus()

        # Refresh to remove filtering and highlighting
        self._refresh_table()
        self.info("Search cleared")

    # -------------------------------------------------------------------------
    # Actions - Open in External Apps
    # -------------------------------------------------------------------------

    def action_open_in_rx(self) -> None:
        """Open the selected file in iZotope RX."""
        file_path = self._get_selected_file_path()
        if not file_path:
            self.info("No file selected")
            return

        try:
            self.logger.info(
                f"Opening file in RX: {file_path.name}", extra={"filepath": file_path}
            )
            subprocess.Popen(
                ["open", "-a", "iZotope RX 11 Audio Editor", str(file_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.info(f"Opening {file_path.name} in RX")
        except Exception as e:
            self.logger.error(
                f"Failed to open file in RX: {file_path.name}",
                extra={"filepath": file_path},
                exc_info=True,
            )
            self.info(f"Error opening RX: {e}")

    def action_open_all_issue_type_in_rx(self) -> None:
        """Open all files with the same issue type in iZotope RX."""
        issue_kind = self._get_current_issue_kind()
        if not issue_kind:
            self.info("No issue selected")
            return

        files = self._get_files_with_issue_kind(issue_kind)
        if not files:
            self.info(f"No files with {issue_kind} issues")
            return

        # Limit to 32 files to avoid overwhelming the system
        MAX_FILES = 32
        if len(files) > MAX_FILES:
            files = files[:MAX_FILES]
            self.logger.warning(
                f"Opening {MAX_FILES}/{len(self._get_files_with_issue_kind(issue_kind))} files in RX (limit reached)",
                extra={
                    "issue_kind": issue_kind,
                    "total_files": len(self._get_files_with_issue_kind(issue_kind)),
                },
            )
            self.info(
                f"Opening first {MAX_FILES} {issue_kind} issues in RX "
                f"({len(self._get_files_with_issue_kind(issue_kind))} total)"
            )
        else:
            self.logger.info(
                f"Opening {len(files)} {issue_kind} files in RX",
                extra={"issue_kind": issue_kind, "file_count": len(files)},
            )
            self.info(f"Opening {len(files)} {issue_kind} issues in RX")

        try:
            subprocess.Popen(
                ["open", "-a", "iZotope RX 11 Audio Editor"] + [str(f) for f in files],
            )
        except Exception as e:
            self.info(f"Error opening RX: {e}")

    def action_open_in_myriad(self) -> None:
        """Open the selected file in Myriad."""
        file_path = self._get_selected_file_path()
        if not file_path:
            self.info("No file selected")
            return

        try:
            self.logger.info(
                f"Opening file in Myriad: {file_path.name}",
                extra={"filepath": file_path},
            )
            subprocess.Popen(
                ["open", "-a", "Myriad", str(file_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.info(f"Opening {file_path.name} in Myriad")
        except Exception as e:
            self.logger.error(
                f"Failed to open file in Myriad: {file_path.name}",
                extra={"filepath": file_path},
                exc_info=True,
            )
            self.info(f"Error opening Myriad: {e}")

    def action_open_all_issue_type_in_myriad(self) -> None:
        """Open all files with the same issue type in Myriad."""
        issue_kind = self._get_current_issue_kind()
        if not issue_kind:
            self.info("No issue selected")
            return

        files = self._get_files_with_issue_kind(issue_kind)
        if not files:
            self.info(f"No files with {issue_kind} issues")
            return

        self.logger.info(
            f"Opening {len(files)} {issue_kind} files in Myriad",
            extra={"issue_kind": issue_kind, "file_count": len(files)},
        )
        self.info(f"Opening {len(files)} {issue_kind} issues in Myriad")

        try:
            subprocess.Popen(
                ["open", "-a", "Myriad"] + [str(f) for f in files],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            self.info(f"Error opening Myriad: {e}")

    def action_reveal_in_finder(self) -> None:
        """Reveal the selected file in Finder."""
        file_path = self._get_selected_file_path()
        if not file_path:
            self.info("No file selected")
            return

        try:
            self.logger.info(
                f"Revealing file in Finder: {file_path.name}",
                extra={"filepath": file_path},
            )
            subprocess.Popen(
                ["open", "-R", str(file_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.info(f"Revealing {file_path.name} in Finder")
        except Exception as e:
            self.logger.error(
                f"Failed to reveal file in Finder: {file_path.name}",
                extra={"filepath": file_path},
                exc_info=True,
            )
            self.info(f"Error revealing in Finder: {e}")

    # -------------------------------------------------------------------------
    # Actions - Audio Processor
    # -------------------------------------------------------------------------

    def action_fix_selected(self) -> None:
        """Show dialog to select fix type for the selected file."""
        filepath = self._get_selected_file_path()
        if not filepath:
            self.info("No file selected")
            return

        row = self.state.audio_data.get_row(filepath)
        if not row:
            self.info("No row selected")
            return

        has_srbd = any(i.kind == "SR/BD" for i in (row.issues or []))
        has_zc = any(i.kind == "ZC" for i in (row.issues or []))
        filename = filepath.name

        def handle_fix_selection(fix_type: str | None) -> None:
            if fix_type is None:
                self.info("Fix cancelled")
                return

            if fix_type == "fix_srbd":
                if not has_srbd:
                    self.info("Selected file has no SR/BD issues")
                    return
                fix_srbd_selected_file(self, self.state, self.audio_processor, filepath)

            elif fix_type == "fix_zc":
                if not has_zc:
                    self.info("Selected file has no ZC issues")
                    return
                fix_zc_selected_file(self, self.state, self.audio_processor, filepath)

            elif fix_type == "fix_all":
                fix_all_issues_selected_file(
                    self, self.state, self.audio_processor, filepath
                )

        # Immediately fix if there's only one issue
        if row.issues and len(row.issues) == 1:
            match row.issues[0].kind:
                case "SR/BD":
                    handle_fix_selection("fix_srbd")
                    return
                case "ZC":
                    handle_fix_selection("fix_zc")
                    return

        # Otherwise show the dialog
        self.push_screen(
            FixTypeDialog(
                filename=filename,
                is_all=False,
                file_count=1,
                has_srbd=has_srbd,
                has_zc=has_zc,
            ),
            handle_fix_selection,
        )

    def action_fix_all_issues(self) -> None:
        """Show dialog to select fix type for all files."""

        srbd_files = self._get_files_with_issue_kind("SR/BD")
        zc_files = self._get_files_with_issue_kind("ZC")

        if self.state.show_all_files:
            all_files = [row.file.filename for row in self.state.audio_data]
        else:
            all_files = [
                row.file.filename for row in self.state.audio_data if row.issues
            ]

        if not all_files:
            self.info("No files to process")
            return

        has_srbd = len(srbd_files) > 0
        has_zc = len(zc_files) > 0

        def handle_fix_selection(fix_type: str | None) -> None:
            if fix_type is None:
                self.info("Fix cancelled")
                return

            if fix_type == "fix_srbd":
                if not srbd_files:
                    self.info("No SR/BD issues found")
                    return
                fix_srbd_all_files(self, self.state, self.audio_processor, srbd_files)

            elif fix_type == "fix_zc":
                if not zc_files:
                    self.info("No ZC issues found")
                    return
                fix_zc_all_files(self, self.state, self.audio_processor, all_files)

            elif fix_type == "fix_all":
                fix_all_issues_all_files(
                    self, self.state, self.audio_processor, all_files
                )

        self.push_screen(
            FixTypeDialog(
                is_all=True, file_count=len(all_files), has_srbd=has_srbd, has_zc=has_zc
            ),
            handle_fix_selection,
        )
