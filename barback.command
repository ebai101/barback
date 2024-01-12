#!/bin/bash
cd $(dirname "$0")
source venv/bin/activate
while true; do
    python3 barback.py "$1" "$2"
    read -p "Press enter to rescan"
    clear
done
