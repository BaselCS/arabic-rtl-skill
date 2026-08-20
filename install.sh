#!/bin/bash
# Universal installer for Arabic RTL Processor
# Works on: Linux, macOS, WSL
# Requires: Python 3.10+, pip, gcc

set -e

echo "🔧 Arabic RTL Processor Installer"
echo "=================================="
echo ""

# Detect OS
OS="$(uname -s)"
case "${OS}" in
    Linux*)     MACHINE=Linux;;
    Darwin*)    MACHINE=Mac;;
    CYGWIN*|MINGW*|MSYS*) MACHINE=Windows;;
    *)          MACHINE="UNKNOWN:${OS}"
esac

echo "Detected OS: ${MACHINE}"
echo ""

# Find Python
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &> /dev/null; then
        version=$("$cmd" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "❌ Python 3.10+ not found. Please install Python first."
    exit 1
fi

echo "Using Python: $($PYTHON --version)"
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "Installing from: ${SCRIPT_DIR}"
echo ""

# Install dependencies
echo "📦 Installing dependencies..."
$PYTHON -m pip install --quiet cython setuptools 2>/dev/null || {
    echo "Trying with --break-system-packages..."
    $PYTHON -m pip install --quiet cython setuptools --break-system-packages 2>/dev/null
}

# Build Cython extension
echo "🔨 Building Cython extension..."
cd "${SCRIPT_DIR}"
$PYTHON setup.py build_ext --inplace 2>&1 | grep -v "running\|building\|copying" || true

# Determine install location
INSTALL_DIR=""
if [ -d "/usr/local/bin" ] && [ -w "/usr/local/bin" ]; then
    INSTALL_DIR="/usr/local/bin"
elif [ -d "$HOME/.local/bin" ]; then
    INSTALL_DIR="$HOME/.local/bin"
    # Add to PATH if not already there
    if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.zshrc" 2>/dev/null || true
        echo "Added ~/.local/bin to PATH (restart shell or run: source ~/.bashrc)"
    fi
else
    mkdir -p "$HOME/.local/bin"
    INSTALL_DIR="$HOME/.local/bin"
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.zshrc" 2>/dev/null || true
    echo "Created ~/.local/bin and added to PATH"
fi

# Create wrapper script
WRAPPER="${INSTALL_DIR}/arabic-rtl"
cat > "${WRAPPER}" << WRAPPER_EOF
#!/bin/bash
# Arabic RTL Processor - Universal Wrapper
# Installed from: ${SCRIPT_DIR}

exec ${PYTHON} "${SCRIPT_DIR}/arabic_rtl_cli.py" "\$@"
WRAPPER_EOF

chmod +x "${WRAPPER}"
echo "✅ Installed wrapper: ${WRAPPER}"

# Also create a .py version for Windows/WSL
WRAPPER_PY="${INSTALL_DIR}/arabic-rtl.py"
cat > "${WRAPPER_PY}" << WRAPPER_PY_EOF
#!/usr/bin/env python3
# Arabic RTL Processor - Python Wrapper
# Installed from: ${SCRIPT_DIR}

import sys
sys.path.insert(0, "${SCRIPT_DIR}")
from arabic_rtl_cli import main
main()
WRAPPER_PY_EOF

chmod +x "${WRAPPER_PY}"
echo "✅ Installed Python wrapper: ${WRAPPER_PY}"

# Create daemon wrapper
DAEMON_WRAPPER="${INSTALL_DIR}/arabic-rtl-daemon"
cat > "${DAEMON_WRAPPER}" << DAEMON_EOF
#!/bin/bash
# Arabic RTL Processor - Daemon Wrapper
# Installed from: ${SCRIPT_DIR}

exec ${PYTHON} "${SCRIPT_DIR}/arabic_rtl_daemon.py" "\$@"
DAEMON_EOF

chmod +x "${DAEMON_WRAPPER}"
echo "✅ Installed daemon wrapper: ${DAEMON_WRAPPER}"

echo ""
echo "=================================="
echo "✅ Installation complete!"
echo ""
echo "Usage (default mode):"
echo "  echo 'السلام عليكم' | arabic-rtl"
echo "  arabic-rtl <<< 'بسم الله الرحمن الرحيم'"
echo "  cat file.txt | arabic-rtl"
echo ""
echo "Daemon mode (optional, faster for repeated calls):"
echo "  arabic-rtl-daemon start"
echo "  echo 'text' | arabic-rtl --daemon"
echo "  arabic-rtl-daemon stop"
echo ""
echo "If 'arabic-rtl' command not found, restart your shell:"
echo "  source ~/.bashrc"
echo "  source ~/.zshrc"
echo "=================================="
