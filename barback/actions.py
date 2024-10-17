import logging
import os


def check_loops(audio_files):
    pass


# finds valid audio files in a directory
def find_valid_audio_files(audio_dir):
    valid_extensions = (".mp3", ".flac", ".wav", ".aif", ".aiff")

    if os.path.isdir(audio_dir):
        try:
            files = [
                {"filename": os.path.join(root, file)}
                for root, _, files in os.walk(audio_dir)
                for file in files
                if file.lower().endswith(valid_extensions)
            ]
        except FileNotFoundError as e:
            logging.error(f"Error opening file: {e}")
            return None
    else:
        logging.error("Must specify a directory")
        return None

    return files
