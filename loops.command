#!/bin/bash
cd $(dirname "$0")
source venv/bin/activate
while true; do
    echo "Checking loops for $1"
    python3 barback.py loops "$1"
    read -p "Press enter to rescan"
    clear
done
