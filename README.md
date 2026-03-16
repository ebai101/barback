# barback

backing the bars - TUI/Web audio validation and repair tool for sample packs

## Automatic install

`curl -s https://raw.githubusercontent.com/ebai101/barback/refs/heads/main/scripts/install.sh | bash -s`

From there, open a terminal and run barback --web or barback --tui.

## Manual install

```
brew install uv
git clone https://github.com/ebai101/barback.git barback
cd barback
uv sync
uv run barback --web "/path/to/samplepack"
```

Loading files can be very slow (30-40s) on the first run after installing, due to librosa JIT compilations that need to run first. subsequent runs should be significantly faster.

The sample pack **should already be named to spec**, using Name Mangler or another similar tool. Barback does not handle batch renaming and relies on proper naming convention and directory structure for some of its checks.

## Usage

Barback checks for 5 kinds of issues:

- SR/BD - sample rate should be 44100Hz, bit depth should be PCM 24-bit
- Silence - no file should have >= 22050 samples of silence at the start/end, one shots additionally should have < 500 samples of silence at the start
- Zero Crossing - files should start and end on a zero crossing
- Loop - files should loop seamlessly and be an exact integer number of bars in length (±1 sample)
- Key signature - all tonal loops should have a key signature at the end of the file

After everything loads you'll see a list of any files in the given folder that have one or many of the issues listed above. You can browse through the files, open them in various applications, preview them, rename, and repair them.

A lot of the functionality is keyboard-based, due to the nature of the Textual framework. There's decent mouse support but it's usually easier to learn the keybinds.

### Browsing

- h j k l (or arrow keys) to navigate
- / (slash) to enter search mode. Type in any search term to filter the list by, press enter to continue browsing, press esc to clear the search
- \` (backtick) to toggle the filetree. Select any directory in the file tree to show only the files in that directory in the list
- Ctrl-Q to quit
- Click any column to sort by that column
- For more guidance, press Ctrl-\ and open the Keys menu to read all available keybinds

### Opening files

You can configure which applications are available to open files with in the config file. The defaults are iZotope RX and Myriad, mapped to 1 and 2 respectively - so, pressing 1 will open the currently selected file in RX, 2 will open it in Myriad. You can add up to 10 applications in the config file.

Pressing Shift with an application's hotkey (Shift-1 for RX, Shift-2 for Myriad, and so on) will open all files with a certain issue type in the application. A dialog will let you pick which issue type you want to open. You can configure a limit for the number of files Barback will open at once - for example, RX can only open 32 files at a time so only the first 32 files will be opened.

### Previewing/renaming

Press Enter on a file to open the preview window. The file will play back automatically, and you can rename it however you wish. Press Enter again to rename the file, or Esc to cancel.

### Repairs

Barback can repair some issues in a given audio file.

- **SR/BD**: Converts to 44/24. Uses Goodhertz Good Dither 3 if the VST/AU is installed, otherwise TPDF dithering is used
- **ZC**: Applies microfades to the start and end - 35 sample fade in, 90 sample fade out
- **Loop**: Truncates/extends the file to match the expected number of samples. This repair will only be done if:
  - a valid BPM is detected
  - the file has "loop" in the name
  - the remainder abs(expected_samples - actual_samples) is less than or equal to 1/4 bar

Press R to repair the selected file. If multiple issues are present, a dialog will allow you to pick which issue to repair. Additionally, Shift-R will apply the selected fix to all files with issues.

Note that all repairs are done in place and are destructive, **there is not currently an undo feature.** Keep a backup of the pack before repairs in case something goes wrong.

## Configuring

The config file is stored at `~/Library/Application Support/barback/config.toml`. The default config will be written there on the first run. Read that file or `config.default.toml` in this repo for more information.

## Logs

Logs can be found at `~/Library/Logs/barback/barback.log`.
