import subprocess
import threading
from collections.abc import Generator
from pathlib import Path
from typing import Any

from textual.app import App
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.coordinate import Coordinate
from textual.widgets import Footer, Header, Input, ProgressBar, Rule, Static

from barback.audio_file import AudioFile
from barback.audio_processor import AudioProcessor
from barback.config import get_config
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
from barback.widgets.dir_tree import DirTree
from barback.widgets.fix_dialog import FixTypeDialog, IssueTypeSelectionDialog
from barback.widgets.playback_dialog import PlaybackDialog
from barback.workers.audio_fixer import (
    fix_all_issues_all_files,
    fix_all_issues_selected_file,
    fix_loop_all_files,
    fix_loop_selected_file,
    fix_silence_all_files,
    fix_silence_selected_file,
    fix_srbd_all_files,
    fix_srbd_selected_file,
    fix_zc_all_files,
    fix_zc_selected_file,
)
from barback.workers.file_processor import init_audio_data
from barback.workers.file_watcher import watch_files


class Barback(App):
    CSS_PATH = "barback.tcss"
    COMMAND_PALETTE_BINDING = "ctrl+backslash"

    BINDINGS = [
        Binding(
            "a",
            "toggle_show_all",
            "Toggle All/Issues",
            tooltip="Switch between viewing all files and only those with issues",
        ),
        Binding(
            "t",
            "toggle_file_tree",
            "Toggle Filetree",
            tooltip="Show/hide the filetree sidebar",
        ),
        Binding(
            "s",
            "rescan_directory",
            "Rescan",
            tooltip="Force a full rescan of the directory",
        ),
        Binding(
            "r", "fix_selected", "Repair", tooltip="Apply fixes to the selected file"
        ),
        Binding(
            "R",
            "fix_all_issues",
            "Repair All",
            tooltip="Apply fixes to all files",
            show=False,
        ),
        Binding(
            "f", "reveal_in_finder", "Reveal", tooltip="Reveal selected file in Finder"
        ),
        Binding(
            "/",
            "enter_search_mode",
            "Search",
            show=False,
            tooltip="Filter files by search term",
        ),
        Binding("escape", "exit_search_mode", "Exit Search", show=False, system=True),
    ]

    def __init__(self, audio_dir: str) -> None:
        super().__init__()
        self.config = get_config()
        self.state = BarbackState(
            audio_dir=Path(audio_dir),
            selected_dir=Path(audio_dir),
        )
        self.audio_processor = AudioProcessor(config=self.config)
        self.logger = get_logger()
        self.logger.info(f"Barback initialized with directory: {audio_dir}")

        self._setup_dynamic_bindings()
        self._register_dynamic_actions()

    def _setup_dynamic_bindings(self) -> None:
        """Setup bindings dynamically from config."""
        for b in self.config.generate_app_bindings():
            self._bindings._add_binding(b)
        self.refresh_bindings()

    def _register_dynamic_actions(self) -> None:
        """Dynamically create action methods for each configured app."""
        for idx, app in enumerate(self.config.apps, start=1):
            if idx > 10:
                break
            action_base = app.display_name.lower().replace(" ", "_")
            self._create_open_action(
                app.display_name, app.application_name, action_base
            )
            self._create_open_all_action(
                app.display_name, app.application_name, action_base
            )

    def _create_open_action(
        self, display_name: str, app_name: str, action_base: str
    ) -> None:
        """Create an action method for opening selected file in an app."""

        def action_method(self_inner: "Barback") -> None:
            file_path = self_inner._get_selected_file_path()
            if not file_path:
                self_inner.info("No file selected")
                return

            try:
                self_inner.logger.info(
                    f"Opening file in {display_name}: {file_path.name}",
                    extra={"filepath": file_path},
                )
                self_inner._run_subprocess(
                    ["open", "-a", app_name, str(file_path)],
                    f"open_in_{action_base}",
                    file_path,
                )
                self_inner.info(f"Opening {file_path.name} in {display_name}")
            except Exception as e:
                self_inner.logger.error(
                    f"Failed to open file in {display_name}: {file_path.name}",
                    extra={"filepath": file_path},
                    exc_info=True,
                )
                self_inner.notify(
                    f"Error opening {display_name}: {e}", severity="error"
                )

        method_name = f"action_open_in_{action_base}"
        setattr(self.__class__, method_name, action_method)
        self.logger.info(f"Bound action {method_name}")

    def _create_open_all_action(
        self, display_name: str, app_name: str, action_base: str
    ) -> None:
        """Create an action method for opening all files with issue type in an app."""

        def action_method(self_inner: "Barback") -> None:
            srbd_files = self_inner._get_audiofiles_with_issue_kind("SR/BD")
            silence_files = self_inner._get_audiofiles_with_issue_kind("Silence")
            zc_files = self_inner._get_audiofiles_with_issue_kind("ZC")
            loop_files = self_inner._get_audiofiles_with_issue_kind("Loop")
            key_sig_files = self_inner._get_audiofiles_with_issue_kind("Key sig")

            has_srbd = len(srbd_files) > 0
            has_silence = len(silence_files) > 0
            has_zc = len(zc_files) > 0
            has_loop = len(loop_files) > 0
            has_key_sig = len(key_sig_files) > 0

            if not (has_srbd or has_silence or has_zc or has_loop or has_key_sig):
                self_inner.info("No issues found")
                return

            # Build info text
            issue_counts = []
            if has_srbd:
                issue_counts.append(f"{len(srbd_files)} SR/BD")
            if has_silence:
                issue_counts.append(f"{len(silence_files)} Silence")
            if has_zc:
                issue_counts.append(f"{len(zc_files)} ZC")
            if has_loop:
                issue_counts.append(f"{len(loop_files)} Loop")
            if has_key_sig:
                issue_counts.append(f"{len(key_sig_files)} Loop")
            info_text = f"Available: {', '.join(issue_counts)}"

            def handle_selection(action: str | None) -> None:
                if action is None:
                    self_inner.info("Cancelled")
                    return

                issue_map = {
                    "open_srbd": ("SR/BD", srbd_files),
                    "open_silence": ("Silence", silence_files),
                    "open_zc": ("ZC", zc_files),
                    "open_loop": ("Loop", loop_files),
                    "open_key_sig": ("Key sig", key_sig_files),
                }

                if action not in issue_map:
                    return

                issue_kind, files = issue_map[action]
                if not files:
                    self_inner.info(f"No {issue_kind} issues found")
                    return

                app_config = next(
                    (
                        app
                        for app in self_inner.config.apps
                        if app.application_name == app_name
                    ),
                    None,
                )
                if not app_config:
                    self_inner.notify(f"App {app_name} not found!", severity="error")
                    return

                self.logger.info(app_config)
                if app_config.max_files and len(files) > app_config.max_files:
                    files = files[: app_config.max_files]
                    self_inner.logger.warning(
                        f"Opening {app_config.max_files}/{len(self_inner._get_audiofiles_with_issue_kind(issue_kind))} files in {display_name}",
                        extra={
                            "issue_kind": issue_kind,
                            "total_files": len(
                                self_inner._get_audiofiles_with_issue_kind(issue_kind)
                            ),
                        },
                    )
                    self_inner.info(
                        f"Opening first {app_config.max_files} {issue_kind} issues in {display_name} ({len(self_inner._get_audiofiles_with_issue_kind(issue_kind))} total)"
                    )
                else:
                    self_inner.logger.info(
                        f"Opening {len(files)} {issue_kind} files in {display_name}",
                        extra={"issue_kind": issue_kind, "file_count": len(files)},
                    )
                    self_inner.info(
                        f"Opening {len(files)} {issue_kind} issues in {display_name}"
                    )

                try:
                    self_inner._run_subprocess(
                        ["open", "-a", app_name] + [str(f.file_path) for f in files],
                        f"open_all_in_{action_base}",
                    )
                except Exception as e:
                    self_inner.notify(
                        f"Error opening {display_name}: {e}", severity="error"
                    )

            # Show dialog
            self_inner.push_screen(
                IssueTypeSelectionDialog(
                    title=f"Open in {display_name} - Select Issue Type",
                    info=info_text,
                    has_srbd=has_srbd,
                    has_silence=has_silence,
                    has_zc=has_zc,
                    has_loop=has_loop,
                    has_key_sig=has_key_sig,
                    action_prefix="open",
                ),
                handle_selection,
            )

        # Bind the method to the class
        method_name = f"action_open_all_in_{action_base}"
        setattr(self.__class__, method_name, action_method)
        self.logger.info(f"Bound action {method_name}")

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
        yield Horizontal(
            Container(
                DirTree(str(self.state.audio_dir), id="dir-tree"),
                id="file-tree-pane",
                classes="hidden",
            ),
            AudioTable(id="table"),
            id="body",
        )
        yield Input(id="search", classes="hidden")
        yield Footer()

    def on_mount(self) -> None:
        """Called when app mounts - kick off the workers."""
        self.info("Starting Barback...")
        self.theme = self.config.theme
        init_audio_data(self, self.state)

    def info(self, text: str) -> None:
        """Update the info box with status messages."""
        info_box = self.query_one("#info", Static)
        info_box.update(text)
        self.logger.debug(text)

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
        progress = self.query_one("#progress", ProgressBar)
        progress.display = False

        if not getattr(self, "_watcher_running", False):
            watch_files(self, self.state)
            self._watcher_running = True

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

        if getattr(self, "current_sort_col", None) == event.column_key:
            self.current_sort_reverse = not self.current_sort_reverse
        else:
            self.current_sort_col = event.column_key
            self.current_sort_reverse = False

        table.sort(event.column_key, reverse=self.current_sort_reverse)

    def on_data_table_row_selected(self, event: AudioTable.RowSelected) -> None:
        """Handle Enter key on table row - open playback dialog."""
        self.action_playback_rename()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes."""
        if event.input.id == "search":
            self.state.search_query = event.value.lower()
            self.info(f"Search: {self.state.search_query or '(empty)'}")
            self._refresh_table()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in search - return focus to table."""
        if event.input.id == "search":
            table = self.query_one("#table", AudioTable)
            table.focus()
            self.info(f"Search: {self.state.search_query or '(empty)'}")

    def on_directory_tree_directory_selected(
        self, event: DirTree.DirectorySelected
    ) -> None:
        self.state.selected_dir = Path(event.path)
        self._refresh_table()

        try:
            relative = self.state.selected_dir.relative_to(self.state.audio_dir)
            label = str(relative) or "."
        except ValueError:
            label = self.state.selected_dir.name

        self.logger.info(f"Filtering files by dir: {label}")

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

        selected_path = self._get_selected_file_path()
        selected_key = str(selected_path) if selected_path else None
        old_cursor_row = table.cursor_row if table.row_count > 0 else 0

        table.clear()

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
                if self.state.search_query in row.file.file_path.name.lower()
            ]

        for row in rows_to_display:
            if row.issues:
                issue_summary = summarize_issues(row.issues)
            else:
                issue_summary = "—"

            # Highlight search query in filename if searching
            filename_display = row.file.file_path.name
            if self.state.search_mode and self.state.search_query:
                filename_display = self._highlight_search(
                    filename_display, self.state.search_query
                )

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
                key=str(row.file.file_path),  # Use full path as key for updates
            )

        sort_col = getattr(self, "current_sort_col", None)
        if sort_col is not None:
            sort_rev = getattr(self, "current_sort_reverse", False)
            table.sort(sort_col, reverse=sort_rev)

        # Restore cursor position, adjusting if needed
        if table.row_count > 0:
            new_cursor_row = 0
            if selected_key:
                try:
                    new_cursor_row = table.get_row_index(selected_key)
                except Exception:
                    new_cursor_row = min(old_cursor_row, table.row_count - 1)
            else:
                new_cursor_row = min(old_cursor_row, table.row_count - 1)
            table.move_cursor(row=new_cursor_row)

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

        lower_text = text.lower()
        start_idx = lower_text.find(query)

        if start_idx == -1:
            return text

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
            filename_display = table.get_cell_at(Coordinate(table.cursor_row, 0))

            # Strip Rich markup if present (from search highlighting)
            # Extract just the filename by removing markup tags
            import re

            filename = re.sub(r"\[.*?\]", "", filename_display)

            for row in self.state.audio_data:
                if row.file.file_path.name == filename:
                    return row.file.file_path

        except Exception as e:
            self.notify(f"Error getting file path: {e}", severity="error")

        return None

    def _get_selected_issue_kind(self) -> str | None:
        """Get the issue kind from the currently selected row."""
        file_path = self._get_selected_file_path()
        if not file_path:
            return None

        row = self.state.audio_data.get_row(file_path)
        if row and row.issues:
            return row.issues[0].kind

        return None

    def _get_audiofiles_with_issue_kind(self, issue_kind: str) -> list[AudioFile]:
        """Get all files that have issues of the specified kind."""
        files = []
        for row in self.state.audio_data:
            if row.issues:
                if any(issue.kind == issue_kind for issue in row.issues):
                    if self.state.search_mode and self.state.search_query:
                        if self.state.search_query in row.file.file_path.name.lower():
                            files.append(row.file)
                    else:
                        files.append(row.file)
        return files

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    def action_cursor_down(self) -> None:
        """Move cursor down in table."""
        if self.state.search_mode:
            return
        table = self.query_one("#table", AudioTable)
        table.action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move cursor up in table."""
        if self.state.search_mode:
            return
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

    def action_toggle_file_tree(self) -> None:
        pane = self.query_one("#file-tree-pane", Container)
        tree = self.query_one("#dir-tree", DirTree)
        table = self.query_one("#table", AudioTable)

        self.state.show_file_tree = not self.state.show_file_tree

        if self.state.show_file_tree:
            pane.remove_class("hidden")
            tree.focus()
            self.logger.info("Showing file tree")
        else:
            pane.add_class("hidden")
            table.focus()
            self.logger.info("Hiding file tree")

    def action_rescan_directory(self) -> None:
        """Force a complete rescan of the audio directory."""
        if not self.state.loaded:
            self.info("Scan already in progress...")
            return

        self.info("Rescanning directory...")
        self.state.loaded = False

        self.state.audio_data.clear()
        self._refresh_table()

        progress = self.query_one("#progress", ProgressBar)
        progress.update(total=100, progress=0)
        progress.display = True

        init_audio_data(self, self.state)

    def action_enter_search_mode(self) -> None:
        """Enter search mode."""
        self.logger.debug("Entered search mode")
        self.state.search_mode = True
        self.state.search_query = ""

        search_input = self.query_one("#search", Input)
        search_input.value = ""
        search_input.focus()

        self.info("Search mode (ESC to exit)")

    def action_exit_search_mode(self) -> None:
        """Exit search mode and clear search."""
        self.logger.debug(
            f"Exited search mode (query was: '{self.state.search_query}')"
        )
        if not self.state.search_mode:
            return

        self.state.search_mode = False
        self.state.search_query = ""

        table = self.query_one("#table", AudioTable)
        table.focus()
        self._refresh_table()
        self.info("Search cleared")

    def action_playback_rename(self) -> None:
        """Open playback/rename dialog for the selected file."""
        file_path = self._get_selected_file_path()
        if not file_path:
            self.info("No file selected")
            return

        def handle_rename_result(result: tuple[bool, str] | None) -> None:
            """Handle the result from the playback dialog."""
            if result is None:
                self.info("Playback cancelled")
                return

            changed, new_name = result

            if changed:
                try:
                    # Construct new path
                    new_path = file_path.parent / f"{new_name}{file_path.suffix}"

                    # Check if target already exists
                    if new_path.exists():
                        self.info(f"File already exists: {new_path.name}")
                        self.logger.warning(
                            f"Rename cancelled - target exists: {new_path.name}",
                            extra={"filepath": file_path, "target": new_path},
                        )
                        return

                    # Perform rename
                    file_path.rename(new_path)

                    self.logger.info(
                        f"Renamed file: {file_path.name} -> {new_path.name}",
                        extra={"old_path": file_path, "new_path": new_path},
                    )
                    self.info(f"Renamed: {file_path.name} → {new_path.name}")

                    # Update state
                    # The file watcher should handle table updates automatically

                except Exception as e:
                    self.logger.error(
                        f"Failed to rename file: {file_path.name}",
                        extra={"filepath": file_path},
                        exc_info=True,
                    )
                    self.notify(f"Error renaming file: {e}", severity="error")
            else:
                self.info("File not renamed")

        # Show the playback dialog
        self.push_screen(PlaybackDialog(file_path), handle_rename_result)

    def _run_subprocess(
        self,
        command: list[str],
        operation: str,
        filepath: Path | None = None,
    ) -> None:
        """
        Run a subprocess command and redirect stdout/stderr to the logger.

        Args:
            command: Command list (e.g., ["open", "-a", "RX", "/path/to/file"])
            operation: Short description for logging (e.g., "open_in_rx")
            filepath: Optional file path for logging context
        """
        try:
            proc = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            def log_stream(stream, level):
                """Read from stream and log each line."""
                for line in iter(stream.readline, ""):
                    if line:
                        line = line.rstrip()
                        if level == "stdout":
                            self.logger.debug(
                                f"[{operation}] {line}",
                                extra={"filepath": filepath, "operation": operation},
                            )
                        else:
                            self.logger.warning(
                                f"[{operation}] {line}",
                                extra={"filepath": filepath, "operation": operation},
                            )
                stream.close()

            # Start threads to consume stdout/stderr
            stdout_thread = threading.Thread(
                target=log_stream, args=(proc.stdout, "stdout"), daemon=True
            )
            stderr_thread = threading.Thread(
                target=log_stream, args=(proc.stderr, "stderr"), daemon=True
            )

            stdout_thread.start()
            stderr_thread.start()

        except Exception:
            self.logger.error(
                f"Failed to start subprocess: {operation}",
                extra={
                    "filepath": filepath,
                    "operation": operation,
                    "command": command,
                },
                exc_info=True,
            )
            raise

    def action_reveal_in_finder(self) -> None:
        file_path = self._get_selected_file_path()
        if not file_path:
            self.info("No file selected")
            return

        try:
            self.logger.info(
                "Revealing file in Finder",
                extra={"filepath": file_path},
            )
            self._run_subprocess(
                ["open", "-R", str(file_path)],
                "reveal_in_finder",
                file_path,
            )
            self.info(f"Revealing {file_path.name} in Finder")
        except Exception as e:
            self.logger.error(
                f"Failed to reveal file: {file_path.name}",
                extra={"filepath": file_path},
                exc_info=True,
            )
            self.notify(f"Error revealing file: {e}", severity="error")

    def action_fix_selected(self) -> None:
        """Show dialog to select fix type for the selected file."""
        file_path = self._get_selected_file_path()
        if not file_path:
            self.info("No file selected")
            return

        row = self.state.audio_data.get_row(file_path)
        if not row:
            self.info("No row selected")
            return

        has_srbd = any(i.kind == "SR/BD" for i in (row.issues or []))
        has_silence = any(i.kind == "Silence" for i in (row.issues or []))
        has_zc = any(i.kind == "ZC" for i in (row.issues or []))
        has_loop = any(i.kind == "Loop" for i in (row.issues or []))
        file_name = file_path.name
        af = row.file

        def handle_fix_selection(fix_type: str | None) -> None:
            if fix_type is None:
                self.info("Fix cancelled")
                return

            if fix_type == "fix_srbd":
                if not has_srbd:
                    self.info("Selected file has no SR/BD issues")
                    return
                fix_srbd_selected_file(self, self.state, self.audio_processor, af)

            elif fix_type == "fix_silence":
                if not has_silence:
                    self.info("Selected file has no silence issues")
                    return
                fix_silence_selected_file(self, self.state, self.audio_processor, af)

            elif fix_type == "fix_zc":
                if not has_zc:
                    self.info("Selected file has no ZC issues")
                    return
                fix_zc_selected_file(self, self.state, self.audio_processor, af)

            elif fix_type == "fix_loop":
                if not has_loop:
                    self.info("Selected file has no Loop issues")
                    return
                fix_loop_selected_file(self, self.state, self.audio_processor, af)

            elif fix_type == "fix_all":
                fix_all_issues_selected_file(self, self.state, self.audio_processor, af)

        # Immediately fix if there's only one issue
        if row.issues and len(row.issues) == 1:
            match row.issues[0].kind:
                case "SR/BD":
                    handle_fix_selection("fix_srbd")
                    return
                case "Silence":
                    handle_fix_selection("fix_silence")
                    return
                case "ZC":
                    handle_fix_selection("fix_zc")
                    return
                case "Loop":
                    handle_fix_selection("fix_loop")
                    return

        # Otherwise show the dialog
        self.push_screen(
            FixTypeDialog(
                filename=file_name,
                is_all=False,
                file_count=1,
                has_srbd=has_srbd,
                has_silence=has_silence,
                has_zc=has_zc,
                has_loop=has_loop,
            ),
            handle_fix_selection,
        )

    def action_fix_all_issues(self) -> None:
        """Show dialog to select fix type for all files."""

        srbd_files = self._get_audiofiles_with_issue_kind("SR/BD")
        silence_files = self._get_audiofiles_with_issue_kind("Silence")
        zc_files = self._get_audiofiles_with_issue_kind("ZC")
        loop_files = self._get_audiofiles_with_issue_kind("Loop")

        if self.state.show_all_files:
            all_files = [row.file for row in self.state.audio_data]
        else:
            all_files = [row.file for row in self.state.audio_data if row.issues]

        if not all_files:
            self.info("No files to process")
            return

        has_srbd = len(srbd_files) > 0
        has_silence = len(silence_files) > 0
        has_zc = len(zc_files) > 0
        has_loop = len(loop_files) > 0

        def handle_fix_selection(fix_type: str | None) -> None:
            if fix_type is None:
                self.info("Fix cancelled")
                return

            if fix_type == "fix_srbd":
                if not srbd_files:
                    self.info("No SR/BD issues found")
                    return
                fix_srbd_all_files(self, self.state, self.audio_processor, srbd_files)

            elif fix_type == "fix_silence":
                if not silence_files:
                    self.info("No silence issues found")
                    return
                fix_silence_all_files(self, self.state, self.audio_processor, zc_files)

            elif fix_type == "fix_zc":
                if not zc_files:
                    self.info("No ZC issues found")
                    return
                fix_zc_all_files(self, self.state, self.audio_processor, zc_files)

            elif fix_type == "fix_loop":
                if not loop_files:
                    self.info("No Loop issues found")
                    return
                fix_loop_all_files(self, self.state, self.audio_processor, loop_files)

            elif fix_type == "fix_all":
                fix_all_issues_all_files(
                    self, self.state, self.audio_processor, all_files
                )

        self.push_screen(
            FixTypeDialog(
                is_all=True,
                file_count=len(all_files),
                has_srbd=has_srbd,
                has_silence=has_silence,
                has_zc=has_zc,
                has_loop=has_loop,
            ),
            handle_fix_selection,
        )
