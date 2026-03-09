#!/usr/bin/env bash
set -e

XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
INSTALL_DIR="$XDG_DATA_HOME/barback"
BIN_DIR="${HOME}/.local/bin"
VENV_DIR="${INSTALL_DIR}/venv"
REPO_URL="https://github.com/username/barback.git"

echo "Starting Barback installation..."

# Verify necessary system tools
for cmd in git python3; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "Error: $cmd is required but not installed."
    exit 1
  fi
done

# Clone the repository or pull updates
if [ -d "$INSTALL_DIR" ]; then
  echo "Updating existing installation in $INSTALL_DIR..."
  git -C "$INSTALL_DIR" pull origin main
else
  echo "Cloning repository..."
  git clone "$REPO_URL" "$INSTALL_DIR"
fi

# Set up the isolated Python environment
echo "Setting up virtual environment..."
python3 -m venv "$VENV_DIR"

# Install application and development tools for web serving
echo "Installing dependencies..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -e "$INSTALL_DIR"
"$VENV_DIR/bin/pip" install --quiet textual-dev

# Generate the global wrapper script
echo "Creating 'barback' command in $BIN_DIR..."
mkdir -p "$BIN_DIR"

WRAPPER_SCRIPT="$BIN_DIR/barback"
cat >"$WRAPPER_SCRIPT" <<EOF
#!/usr/bin/env bash
# Automatically serves the TUI to the web
exec "${VENV_DIR}/bin/textual" serve "${VENV_DIR}/bin/barback" "\$@"
EOF

chmod +x "$WRAPPER_SCRIPT"

echo "Installation complete! Ensure $BIN_DIR is in your PATH."
