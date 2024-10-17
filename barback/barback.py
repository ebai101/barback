import os


def check_loops(audio_files):
    pass


def load_audio_files(audio_dir, message_box):
    valid_extensions = (".mp3", ".flac", ".wav", ".aif", ".aiff")
    if os.path.isdir(audio_dir):
        try:
            files = [
                (os.path.join(root, file),)
                for root, _, files in os.walk(audio_dir)
                for file in files
                if file.lower().endswith(valid_extensions)
            ]
            if not files:
                message_box.update_message(
                    "No valid audio files found in the directory."
                )
                return None
            return [("Filename",)] + files
        except FileNotFoundError as e:
            message_box.update_message(f"Error opening file: {e}")
            return None
    else:
        message_box.update_message("Must specify a valid directory")
        return None
