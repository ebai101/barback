from dataclasses import dataclass
from pathlib import Path

from barback.audio_data import AudioData


@dataclass
class BarbackState:
    audio_dir: Path
    selected_dir: Path
    audio_data: AudioData = AudioData()
    loaded: bool = False
    show_all_files: bool = False
    search_mode: bool = False
    search_query: str = ""
    show_file_tree: bool = False
