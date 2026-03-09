#!/usr/bin/env bash
set -e

INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/barback"
VENV_DIR="$INSTALL_DIR/venv"
UPDATE_STAMP="$INSTALL_DIR/.last_update"

DO_UPDATE=false
FORCE_UPDATE=false

ARGS=()
for arg in "$@"; do
  if [ "$arg" = "--update" ]; then
    FORCE_UPDATE=true
    DO_UPDATE=true
  else
    ARGS+=("$arg")
  fi
done

if [ "$FORCE_UPDATE" = false ]; then
  if [ ! -f "$UPDATE_STAMP" ]; then
    DO_UPDATE=true
  else
    LAST_RUN=$(stat -f "%m" "$UPDATE_STAMP" 2>/dev/null || stat -c "%Y" "$UPDATE_STAMP")
    NOW=$(date +%s)

    if [ $((NOW - LAST_RUN)) -gt 86400 ]; then
      DO_UPDATE=true
    fi
  fi
fi

if [ "$DO_UPDATE" = true ]; then
  if [ "$FORCE_UPDATE" = true ]; then
    echo "Forcing Barback update check..."
  fi

  if cd "$INSTALL_DIR" && git fetch origin main --quiet 2>/dev/null; then
    LOCAL=$(git rev-parse HEAD)
    REMOTE=$(git rev-parse origin/main)

    if [ "$LOCAL" != "$REMOTE" ]; then
      echo "Installing new version..."
      git pull origin main --quiet

      "$VENV_DIR/bin/pip" install --quiet -e "$INSTALL_DIR"
      echo "Update complete."
    elif [ "$FORCE_UPDATE" = true ]; then
      echo "Barback is already up to date."
    fi
    touch "$UPDATE_STAMP"
  elif [ "$FORCE_UPDATE" = true ]; then
    echo "Failed to check for updates. Please check your internet connection."
  fi
fi

exec "$VENV_DIR/bin/textual" serve "$VENV_DIR/bin/barback" "${ARGS[@]}"
