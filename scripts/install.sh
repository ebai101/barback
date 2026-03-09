#!/usr/bin/env bash
set -e

XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
INSTALL_DIR="$XDG_DATA_HOME/barback"
BIN_DIR="${HOME}/.local/bin"
VENV_DIR="${INSTALL_DIR}/venv"
REPO_URL="git@github.com:ebai101/barback.git"

echo "Starting Barback installation..."

if ! command -v git &>/dev/null; then
  echo "Error: git is required but not installed."
  exit 1
fi

if ! command -v uv &>/dev/null; then
  echo "Installing uv (fast Python package manager)..."
  curl -LsSf https://astral.sh/uv/install.sh | sh

  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi

if [ -d "$INSTALL_DIR" ]; then
  echo "Updating existing installation..."
  git -C "$INSTALL_DIR" pull origin main --quiet
else
  echo "Cloning repository..."
  mkdir -p "$INSTALL_DIR"
  git clone --quiet "$REPO_URL" "$INSTALL_DIR"
fi

echo "Setting up virtual environment with Python 3.12..."
uv venv --python 3.12 "$VENV_DIR"

echo "Installing dependencies..."
uv pip install --python "$VENV_DIR" -e "$INSTALL_DIR"
uv pip install --python "$VENV_DIR" textual-dev

echo "Copying launcher script to $BIN_DIR/barback..."
mkdir -p "$BIN_DIR"
cp "$INSTALL_DIR/scripts/launcher.sh" "$BIN_DIR/barback"
chmod +x "$BIN_DIR/barback"

echo "Installation complete! Ensure $BIN_DIR is in your PATH."
echo "Run 'barback' to start the application, or 'barback --update' to force an update check."
