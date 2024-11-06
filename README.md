# barback

back of the bar

## todo

screens for better keybinds/easier display, streamlined mode handling
- i think i need multiple screens?
- at least multiple tables. different instances to handle different data

fix find_duplicates
- use debugger to watch memory usage

implement extender
- some form of input for bpm? infer?
- file writing to temp dir or maybe just overwrite
- this might just need to be a separate program

implement file watcher

add more cool shit

protools session processor?
something to make better stems out of pt sessions


## first usage notes

clickable column headers for sorting
need validate path on open
open all might be not respect selected dir
have to reopen to rescan finalizer
file updater is gonna be needed

renaming files crashes:
no such file or directory when trying to find old files

if no such file, we should remove the audiofile instance from the lib

but creation/removal of instances in the table should occur based on messages from the file handler

maybe an audio display widget below the file tree? if at all possible lol