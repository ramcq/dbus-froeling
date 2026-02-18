#!/bin/bash
# Installation script for dbus-froeling on Venus OS

# Configuration
SERVICE_NAME="dbus-froeling"
INSTALL_PATH="/data/etc/${SERVICE_NAME}"
SERVICE_PATH="/service/${SERVICE_NAME}"

echo "Installing ${SERVICE_NAME} to Venus OS..."

# Check if running on Venus OS
if [ ! -d "/data" ]; then
    echo "Error: /data partition not found. Are you running on Venus OS?"
    exit 1
fi

# Create installation directory
echo "Creating installation directory..."
mkdir -p "${INSTALL_PATH}"
mkdir -p "${INSTALL_PATH}/service"
mkdir -p "${INSTALL_PATH}/service/log"

# Copy main script
echo "Copying service files..."
cp dbus-froeling.py "${INSTALL_PATH}/"
chmod +x "${INSTALL_PATH}/dbus-froeling.py"

# Copy velib_python if not already present
if [ ! -d "${INSTALL_PATH}/ext/velib_python" ]; then
    echo "Downloading velib_python..."
    mkdir -p "${INSTALL_PATH}/ext"
    cd "${INSTALL_PATH}/ext"
    git clone https://github.com/victronenergy/velib_python.git
    cd -
fi

# Create run script
cat > "${INSTALL_PATH}/service/run" << 'RUNSCRIPT'
#!/bin/sh
exec 2>&1
exec python3 /data/etc/dbus-froeling/dbus-froeling.py
RUNSCRIPT
chmod +x "${INSTALL_PATH}/service/run"

# Create log run script
cat > "${INSTALL_PATH}/service/log/run" << 'LOGSCRIPT'
#!/bin/sh
exec multilog t s25000 n4 /var/log/dbus-froeling
LOGSCRIPT
chmod +x "${INSTALL_PATH}/service/log/run"

# Create configuration file if not already present
if [ ! -f "${INSTALL_PATH}/config.env" ]; then
    cat > "${INSTALL_PATH}/config.env" << 'CONFIG'
# Froeling T4e Configuration
FROELING_HOST=192.168.1.245
FROELING_PORT=502
FROELING_DEVICE_ID=2
UPDATE_INTERVAL=10000
CONFIG
    echo "Configuration file created at ${INSTALL_PATH}/config.env"
    echo "Edit this file to customize your Froeling connection settings"
else
    echo "Configuration file already exists, skipping"
fi

# Create rc.local to persist service across reboots
if [ ! -f "/data/rc.local" ]; then
    cat > "/data/rc.local" << 'RCLOCAL'
#!/bin/bash
# Restore dbus-froeling service symlink
ln -sf /data/etc/dbus-froeling/service /service/dbus-froeling
RCLOCAL
    chmod +x "/data/rc.local"
    echo "Created /data/rc.local"
else
    # Add to existing rc.local if not already present
    if ! grep -q "dbus-froeling" /data/rc.local; then
        echo "ln -sf /data/etc/dbus-froeling/service /service/dbus-froeling" >> /data/rc.local
        echo "Added dbus-froeling to /data/rc.local"
    fi
fi

# Install pymodbus if not present
echo "Checking for pymodbus..."
if ! python3 -c "import pymodbus" 2>/dev/null; then
    echo "Installing pymodbus..."
    opkg update
    opkg install python3-pymodbus
fi

echo ""
echo "Installation complete!"
echo ""
echo "To start the service:"
echo "  ln -s ${INSTALL_PATH}/service ${SERVICE_PATH}"
echo ""
echo "To check service status:"
echo "  svstat ${SERVICE_PATH}"
echo ""
echo "To view logs:"
echo "  tail -f /var/log/dbus-froeling/current"
echo ""
echo "To stop the service:"
echo "  rm ${SERVICE_PATH}"
echo "  svc -d ${SERVICE_PATH}"
echo ""
