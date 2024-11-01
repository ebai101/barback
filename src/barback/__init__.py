import sys

from barback.app import Barback


def main() -> None:
    if len(sys.argv) != 2:
        print("Must supply an audio directory")
        sys.exit(1)
    audio_dir = sys.argv[1]
    app = Barback(audio_dir)
    app.run()


if __name__ == "__main__":
    main()
