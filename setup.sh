#!/bin/bash
# Quick setup script for dbus-froeling
# Run this in the same directory as dbus-froeling.py

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Setting up dbus-froeling in ${SCRIPT_DIR}..."

# Create ext directory
mkdir -p "${SCRIPT_DIR}/ext"

# Download velib_python if not present
if [ ! -d "${SCRIPT_DIR}/ext/velib_python" ]; then
    echo "Downloading velib_python..."
    cd "${SCRIPT_DIR}/ext"
    
    # Try git first
    if command -v git &> /dev/null; then
        git clone https://github.com/victronenergy/velib_python.git
    else
        # Fallback to wget + tar if git not available
        echo "Git not found, downloading archive..."
        wget https://github.com/victronenergy/velib_python/archive/refs/heads/master.tar.gz -O velib_python.tar.gz
        tar -xzf velib_python.tar.gz
        mv velib_python-master velib_python
        rm velib_python.tar.gz
    fi
    
    cd "${SCRIPT_DIR}"
    echo "velib_python downloaded successfully"
else
    echo "velib_python already exists, skipping download"
fi

echo ""
echo "Setup complete! velib_python is in ${SCRIPT_DIR}/ext/velib_python"
echo ""
echo "Now you can run:"
echo "  python3 dbus-froeling.py"
