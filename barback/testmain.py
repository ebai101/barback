import os
import sys
import actions
import tui


def main(action, audio_dir, bpm=120):
    barback_tui = tui.BarbackTui()
    barback_tui.run()

    audio_files = actions.find_valid_audio_files(barback_tui, audio_dir)
    if audio_files is None:
        sys.exit(1)

    # if action == "loops":
    #     print(f"Checking loops for {audio_dir}")
    #     actions.check_loops(audio_files)


if __name__ == "__main__":
    main("loops", sys.argv[1])
    # if len(sys.argv) < 3:
    #     print("specify an action and a folder")
    #     sys.exit(1)
    # action = sys.argv[1]
    # audio_dir = os.path.abspath(sys.argv[2])

    # if action == "extend":
    #     if len(sys.argv) < 4:
    #         print("specify an action, folder and bpm")
    #         sys.exit(1)
    #     bpm = sys.argv[3]
    #     main(action, audio_dir, bpm)
    # else:
    #     main(action, audio_dir)
