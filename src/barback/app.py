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

    # -------------------------------------------------------------------------
    # Actions (stubs for future features)
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
