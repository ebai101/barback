#!/bin/bash
echo "Finding duplicates for $1"
cd $(dirname "$0")
source venv/bin/activate
python3 duplicates.py "$1"
read -n 1 -s -r -p "Press any key to continue..."