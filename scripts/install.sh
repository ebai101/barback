#!/usr/bin/env bash
set -e

XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
INSTALL_DIR="$XDG_DATA_HOME/barback"
BIN_DIR="${HOME}/.local/bin"
VENV_DIR="${INSTALL_DIR}/venv"
REPO_URL="https://github.com/username/barback.git"

echo "Starting Barback installation..."

for cmd in git python3; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "Error: $cmd is required but not installed."
    exit 1
  fi
done

if [ -d "$INSTALL_DIR" ]; then
  echo "Updating existing installation..."
  git -C "$INSTALL_DIR" pull origin main --quiet
else
  echo "Cloning repository..."
  mkdir -p "$INSTALL_DIR"
  git clone --quiet "$REPO_URL" "$INSTALL_DIR"
fi

echo "Setting up virtual environment..."
python3 -m venv "$VENV_DIR"

echo "Installing dependencies..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -e "$INSTALL_DIR"
"$VENV_DIR/bin/pip" install --quiet textual-dev

echo "Symlinking launcher to $BIN_DIR/barback..."
mkdir -p "$BIN_DIR"

cp "$INSTALL_DIR/scripts/launcher.sh" "$BIN_DIR/barback"
chmod +x "$BIN_DIR/barback"

echo "Installation complete! Ensure $BIN_DIR is in your PATH."
echo "Run 'barback' to start the application."
