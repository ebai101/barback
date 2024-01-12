# barback

## install
```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## usage
```
# check loops
./barback.command loops "/path/to/folder/of/loops"

# find duplicates
./barback.command duplicates "/path/to/folder/of/loops"
```

## finder action

open Automator and create a Quick Action

for alacritty, add a Run Shell Script block with this content:
```
/opt/homebrew/bin/alacritty -e "/path/to/barback.command" loops "$1"
```

for Terminal.app, add a Run Applescript block with this content:
```
on run {input, parameters}

	set p to POSIX path of input
	tell application "Terminal"
		activate
		do script "/path/to/barback.command" & " loops " & quoted form of p
	end tell

	return input
end run
```

save as Check Loops. create another one called Find Duplicates with the same command, replacing "loops" with "duplicates"
