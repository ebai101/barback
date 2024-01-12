# audio-duplicates

Scans a directory for duplicate audio files. Uses a weighted average of the zero crossing similarity, constant-Q chromagram similarity and spectral contrast similarity as a metric. This allows the script to detect duplicates that may have small differences such as fades, truncation, bit rate/sample rate changes and normalization.

https://github.com/ebai101/audio-duplicates/assets/11427711/c5024cd2-13ab-44bf-be08-dc78e389527b

Requires Python 3.10. Clickable links require Keyboard Maestro, and a terminal that supports them (not Terminal.app).

# Usage

```
git clone https://github.com/ebai101/audio-duplicates.git
cd audio-duplicates
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

You can run the script from the terminal now, as long as you're in the virtual env:

```
./duplicates.py /path/to/folder/of/sounds
```

# Clickable links

You need Keyboard Maestro for the links to reveal files in the Finder. You also need to be running one of [these terminal emulators](https://github.com/Alhadis/OSC8-Adoption/), which unfortunately does not include Terminal.app (yet.) The macro I use looks like this:

![image](https://github.com/ebai101/audio-duplicates/assets/11427711/5b0ce0c9-b41f-4559-bbe5-f6fe23f00942)

The macro must be enabled globally and must be able to be triggered by URL. You want to copy the UUID of your specific macro (the highlighted text in the above image) and replace the UUID on line 128 of `duplicates.py` with your own UUID.
