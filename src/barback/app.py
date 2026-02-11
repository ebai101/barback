import subprocess
from collections.abc import Generator
from pathlib import Path
from typing import Any

from textual.app import App
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Footer, Header, ProgressBar, Rule, Static

from barback.state import BarbackState
from barback.util.messages import (
    BarbackLoaded,
    ProgressBarAdvance,
    ProgressBarUpdate,
    TableUpdate,
)
from barback.validation import summarize_issues
from barback.widgets.audio_table import AudioTable
from barback.widgets.file_tree import FileTree
from barback.widgets.info_box import InfoBox
from barback.workers.file_watcher import watch_files
from barback.workers.init_audio_data import init_audio_data


class Barback(App):
    CSS_PATH = "barback.tcss"
    BINDINGS = [
        Binding("q", "quit", "Quit", show=False, priority=True),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("a", "toggle_show_all", "Toggle All/Issues"),
        Binding("x", "open_in_rx", "RX"),
        Binding("X", "open_all_issue_type_in_rx", "RX (All Issue Type)"),
        Binding("m", "open_in_myriad", "Myriad"),
        Binding("M", "open_all_issue_type_in_myriad", "Myriad (All Issue Type)"),
        Binding("f", "reveal_in_finder", "Finder"),
    ]

    def __init__(self, audio_dir: str) -> None:
        super().__init__()
        self.state = BarbackState(
            audio_dir=Path(audio_dir),
            selected_dir=Path(audio_dir),
        )

    def compose(self) -> Generator[Any, Any, None]:
        """Build the UI layout."""
        yield Header()
        yield Container(
            InfoBox(id="info"),
            Static(),  # Spacer
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

    def on_mount(self) -> None:
        """Called when app mounts - kick off the workers."""
        self.theme = "tokyo-night"
        self.info("Starting Barback...")

        # Start the initial scan
        init_audio_data(self, self.state)

    def info(self, text: str) -> None:
        """Update the info box with status messages."""
        info_box = self.query_one("#info", InfoBox)
        info_box.update(text)

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

        # Populate table
        for row in rows_to_display:
            # Format issue summary
            if row.issues:
                issue_summary = summarize_issues(row.issues)
            else:
                issue_summary = "—"

            # Add row to table
            table.add_row(
                row.file.filename.name,
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

        # Update info with stats
        total_files = len(self.state.audio_data)
        files_with_issues = len(rows_to_display)

        if self.state.loaded:
            self.info(f"{total_files} files scanned, {files_with_issues} with issues")

    def _get_selected_file_path(self) -> Path | None:
        """Get the file path of the currently selected row."""
        table = self.query_one("#table", AudioTable)

        if table.row_count == 0:
            return None

        try:
            # Get the filename from the first column of the current row
            filename = table.get_cell_at((table.cursor_row, 0))

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
                    files.append(row.file.filename)
        return files

    # -------------------------------------------------------------------------
    # Actions - Basic Navigation
    # -------------------------------------------------------------------------

    def action_cursor_down(self) -> None:
        """Move cursor down in table."""
        table = self.query_one("#table", AudioTable)
        table.action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move cursor up in table."""
        table = self.query_one("#table", AudioTable)
        table.action_cursor_up()

    def action_toggle_show_all(self) -> None:
        """Toggle between showing all files and only files with issues."""
        self.state.show_all_files = not self.state.show_all_files
        self._refresh_table()

        if self.state.show_all_files:
            self.info("Showing all files")
        else:
            self.info("Showing only files with issues")

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
            subprocess.Popen(
                ["open", "-a", "iZotope RX 11 Audio Editor", str(file_path)]
            )
            self.info(f"Opening {file_path.name} in RX")
        except Exception as e:
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
            self.info(
                f"Opening first {MAX_FILES} {issue_kind} issues in RX "
                f"({len(self._get_files_with_issue_kind(issue_kind))} total)"
            )
        else:
            self.info(f"Opening {len(files)} {issue_kind} issues in RX")

        try:
            subprocess.Popen(
                ["open", "-a", "iZotope RX 11 Audio Editor"] + [str(f) for f in files],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
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
            # Adjust app name as needed for your Myriad installation
            subprocess.Popen(
                ["open", "-a", "Myriad", str(file_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.info(f"Opening {file_path.name} in Myriad")
        except Exception as e:
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
            subprocess.Popen(
                ["open", "-R", str(file_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.info(f"Revealing {file_path.name} in Finder")
        except Exception as e:
            self.info(f"Error revealing in Finder: {e}")
