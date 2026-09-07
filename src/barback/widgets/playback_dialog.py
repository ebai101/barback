from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.timer import Timer
from textual.widgets import Button, Footer, Input, ProgressBar, Static

from barback.util.logger import get_logger


class PlaybackDialog(ModalScreen[tuple[bool, str] | None]):
    """Dialog for audio playback and file renaming."""

    BINDINGS = (
        Binding("escape", "dismiss", "Cancel"),
        Binding("ctrl+p", "toggle_playback", "Play/Pause"),
        Binding("ctrl+l", "toggle_loop", "Toggle Loop"),
        Binding("return", "submit", "Rename"),
    )

    def __init__(self, file_path: Path) -> None:
        """Initialize the playback dialog.

        Args:
            file_path: Path to the audio file to play
        """
        super().__init__()
        self.file_path = file_path
        self.logger = get_logger()

        # Audio state
        self.audio_data: np.ndarray | None = None
        self.sample_rate: int = 44100
        self.stream: sd.OutputStream | None = None
        self.is_playing: bool = False
        self.is_looping: bool = "loop" in str(file_path).lower()
        self.position: int = 0
        self.duration: float = 0.0

        # UI update timer
        self.update_timer: Timer | None = None

        # Original filename for comparison
        self.original_name = file_path.stem

    def compose(self) -> ComposeResult:
        """Build the dialog UI."""
        with Vertical(id="playback_dialog"):
            yield Static(f"Playing: {self.file_path.name}", id="playback_title")

            # Playback controls
            with Horizontal(id="playback_controls"):
                yield Button("⏸ Pause", id="play_pause_btn", variant="primary")
                yield Button(
                    f"Loop: {'ON' if self.is_looping else 'OFF'}",
                    id="loop_btn",
                    variant="success" if self.is_looping else "default",
                )

            # Position indicator
            yield Static("0:00 / 0:00", id="position_display")
            yield ProgressBar(total=100, show_eta=False, id="position_bar")

            # Rename input
            yield Static("Rename:", id="rename_label")
            yield Input(
                value=self.original_name,
                id="rename_input",
                select_on_focus=False,
            )
            yield Footer()

    def on_mount(self) -> None:
        """Load audio and start playback when mounted."""
        try:
            # Load audio file
            self.logger.info(f"Loading audio file: {self.file_path}")
            self.audio_data, self.sample_rate = sf.read(self.file_path, always_2d=True)
            self.duration = len(self.audio_data) / self.sample_rate

            # Update position bar
            position_bar = self.query_one("#position_bar", ProgressBar)
            position_bar.update(total=len(self.audio_data))

            # Focus the rename input
            rename_input = self.query_one("#rename_input", Input)
            rename_input.focus()
            rename_input.action_end()  # Move cursor to end

            # Start playback automatically
            self._start_playback()

            # Start UI update timer (update every 100ms)
            self.update_timer = self.set_interval(0.1, self._update_position_display)

        except Exception as e:
            self.logger.exception("Failed to load audio file:")
            self.notify(f"Error loading audio: {e}", severity="error")
            self.dismiss(None)

    def _start_playback(self) -> None:
        """Start or resume audio playback."""
        if self.audio_data is None:
            return

        try:
            # Create output stream with callback
            self.stream = sd.OutputStream(
                samplerate=self.sample_rate,
                channels=self.audio_data.shape[1],
                callback=self._audio_callback,
                finished_callback=self._playback_finished,
            )
            self.stream.start()
            self.is_playing = True

            # Update button
            play_pause_btn = self.query_one("#play_pause_btn", Button)
            play_pause_btn.label = "⏸ Pause"

            self.logger.debug(f"Started playback: {self.file_path.name}")

        except Exception as e:
            self.logger.exception("Failed to start playback:")
            self.notify(f"Playback error: {e}", severity="error")

    def _stop_playback(self) -> None:
        """Pause audio playback."""
        if self.stream and self.is_playing:
            self.stream.stop()
            self.is_playing = False

            # Update button
            play_pause_btn = self.query_one("#play_pause_btn", Button)
            play_pause_btn.label = "▶ Play"

            self.logger.debug(f"Paused playback: {self.file_path.name}")

    def _audio_callback(
        self, outdata: np.ndarray, frames: int, time_info, status
    ) -> None:
        """Callback for audio stream - fills output buffer."""
        if status:
            self.logger.warning(f"Audio callback status: {status}")

        if self.audio_data is None:
            outdata.fill(0)
            return

        # Calculate how many frames to read
        remaining = len(self.audio_data) - self.position
        frames_to_read = min(frames, remaining)

        if frames_to_read > 0:
            outdata[:frames_to_read] = (
                self.audio_data[self.position : self.position + frames_to_read]
                * 0.5  # play at -6dB
            )
            self.position += frames_to_read

        # Fill remainder with silence if needed
        if frames_to_read < frames:
            outdata[frames_to_read:].fill(0)

            # Handle looping
            if self.is_looping and remaining <= 0:
                self.position = 0  # Reset to beginning

    def _playback_finished(self) -> None:
        """Called when playback reaches the end."""
        if not self.is_attached:
            # app is probably quitting, return
            return
        if not self.is_looping:
            self.is_playing = False
            play_pause_btn = self.query_one("#play_pause_btn", Button)
            play_pause_btn.label = "▶ Play"
            self.position = 0  # Reset position

    def _update_position_display(self) -> None:
        """Update the position display and progress bar."""
        if self.audio_data is None:
            return

        # Update progress bar
        position_bar = self.query_one("#position_bar", ProgressBar)
        position_bar.update(progress=self.position)

        # Update time display
        current_time = self.position / self.sample_rate
        total_time = self.duration

        current_str = self._format_time(current_time)
        total_str = self._format_time(total_time)

        position_display = self.query_one("#position_display", Static)
        position_display.update(f"{current_str} / {total_str}")

    @staticmethod
    def _format_time(seconds: float) -> str:
        """Format seconds as M:SS."""
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}:{secs:02d}"

    def action_toggle_playback(self) -> None:
        """Toggle play/pause."""
        if self.is_playing:
            self._stop_playback()
        else:
            self._start_playback()

    def action_toggle_loop(self) -> None:
        """Toggle loop on/off."""
        self.is_looping = not self.is_looping

        # Update button
        loop_btn = self.query_one("#loop_btn", Button)
        loop_btn.label = f"Loop: {'ON' if self.is_looping else 'OFF'}"
        loop_btn.variant = "success" if self.is_looping else "default"

        self.logger.debug(f"Loop toggled: {self.is_looping}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "play_pause_btn":
            self.action_toggle_playback()
        elif event.button.id == "loop_btn":
            self.action_toggle_loop()

    def on_input_submitted(self) -> None:
        """Handle Enter key - rename file and close."""
        rename_input = self.query_one("#rename_input", Input)
        new_name = rename_input.value.strip()

        # Check if name changed
        if not new_name:
            self.notify("Filename cannot be empty", severity="warning")
            return

        # Clean up and dismiss
        self._cleanup()

        # Return (name_changed, new_name)
        changed = new_name != self.original_name
        self.dismiss((changed, new_name))

    def action_dismiss(self) -> None:  # ty:ignore[invalid-method-override]
        """Handle Escape key - cancel without renaming."""
        self._cleanup()
        self.dismiss(None)

    def _cleanup(self) -> None:
        """Clean up audio resources."""
        # Stop timer
        if self.update_timer:
            self.update_timer.stop()

        # Stop and close audio stream
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        self.is_playing = False
        self.logger.debug(f"Cleaned up playback resources: {self.file_path.name}")
