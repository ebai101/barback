#!/usr/bin/env bash
set -e

INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/barback"
VENV_DIR="$INSTALL_DIR/venv"
UPDATE_STAMP="$INSTALL_DIR/.last_update"

DO_UPDATE=false
if [ ! -f "$UPDATE_STAMP" ]; then
  DO_UPDATE=true
else
  LAST_RUN=$(stat -f "%m" "$UPDATE_STAMP" 2>/dev/null || stat -c "%Y" "$UPDATE_STAMP")
  NOW=$(date +%s)

  if [ $((NOW - LAST_RUN)) -gt 86400 ]; then
    DO_UPDATE=true
  fi
fi

if [ "$DO_UPDATE" = true ]; then
  echo "Checking for Barback updates..."

  # Run fetch with a 5-second timeout to prevent hanging on bad networks
  if cd "$INSTALL_DIR" && timeout 5 git fetch origin main --quiet 2>/dev/null; then
    LOCAL=$(git rev-parse HEAD)
    REMOTE=$(git rev-parse origin/main)

    if [ "$LOCAL" != "$REMOTE" ]; then
      echo "Installing new version..."
      git pull origin main --quiet

      # Re-install to catch any new dependencies added to pyproject.toml
      "$VENV_DIR/bin/pip" install --quiet -e "$INSTALL_DIR"
    fi
    touch "$UPDATE_STAMP"
  fi
fi

exec "$VENV_DIR/bin/textual" serve "$VENV_DIR/bin/barback" "$@"
