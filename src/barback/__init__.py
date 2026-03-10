import sys
from pathlib import Path

from barback.app import Barback
from barback.config import get_config
from barback.util.logger import get_logger


def main() -> None:
    config = get_config()
    logger = get_logger()

    logger.setLevel(config.log_level)
    logger.info("=" * 80)
    logger.info(f"Loaded config from {config.get_config_path()}")

    if len(sys.argv) != 2:
        logger.error("Invalid arguments - missing audio directory")
        print("Usage: barback <audio_directory>")
        sys.exit(1)

    audio_dir = sys.argv[1]
    audio_path = Path(audio_dir)

    if not audio_path.exists():
        logger.error(f"Directory does not exist: {audio_dir}")
        print(f"Error: Directory '{audio_dir}' does not exist")
        sys.exit(1)

    if not audio_path.is_dir():
        logger.error(f"Path is not a directory: {audio_dir}")
        print(f"Error: '{audio_dir}' is not a directory")
        sys.exit(1)

    logger.info(f"Starting Barback with directory: {audio_path.resolve()}")

    try:
        app = Barback(str(audio_path.resolve()))
        app.run()
    except KeyboardInterrupt:
        logger.info("Barback interrupted by user (Ctrl+C)")
    except Exception as e:
        logger.critical("Barback crashed with unhandled exception", exc_info=True)
        raise e
    finally:
        logger.info("Barback shutting down")


if __name__ == "__main__":
    main()
