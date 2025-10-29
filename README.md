# dbus-froeling

Venus OS dbus service for Froeling T4e pellet boiler monitoring via Modbus TCP.

Publishes buffer tank temperatures and boiler status to Venus OS for integration with VRM portal and Victron energy management.

## Features

- **Two temperature sensors** for Venus OS:
  - Buffer tank top temperature
  - Buffer tank bottom temperature
  - Appears in Venus OS GUI and VRM portal
  - Proper device instances for clean organization

- **Boiler status monitoring**:
  - System operating mode (Automatic, Domestic Hot Water, etc.)
  - Furnace state (Heating, Off, Ignition, etc.)
  - Simple boolean: Boiler Operating (yes/no)
  - Available via dbus and published to MQTT

- **Robust implementation**:
  - Automatic reconnection on connection loss
  - Connection state monitoring
  - Based on official Victron Python patterns
  - Uses velib_python for proper dbus integration

## Installation

### Prerequisites

- Venus OS (tested on v2.90+)
- Froeling T4e with Modbus TCP enabled
- Network connectivity between Venus OS and Froeling

### Quick Install

1. Copy files to Venus OS:
```bash
scp dbus-froeling.py install.sh root@<venus-ip>:/data/tmp/
```

2. SSH to Venus OS and run installer:
```bash
ssh root@<venus-ip>
cd /data/tmp
./install.sh
```

3. Edit configuration if needed:
```bash
vi /data/etc/dbus-froeling/config.env
```

4. Start the service:
```bash
ln -s /data/etc/dbus-froeling/service /service/dbus-froeling
```

5. Check it's running:
```bash
svstat /service/dbus-froeling
tail -f /var/log/dbus-froeling/current
```

## Configuration

Edit `/data/etc/dbus-froeling/config.env`:

```bash
# Froeling T4e Configuration
FROELING_HOST=192.168.1.245     # IP address of your Froeling
FROELING_PORT=502               # Modbus TCP port (default 502)
FROELING_DEVICE_ID=2            # Modbus device/slave ID (default 2)
UPDATE_INTERVAL=5000            # Update interval in milliseconds
```

After changing configuration, restart the service:
```bash
svc -t /service/dbus-froeling
```

## Dbus Paths

### Buffer Top Temperature
Service: `com.victronenergy.temperature.froeling_buffer_top`

- `/Temperature` - Temperature in °C
- `/Status` - 0=Ok, 1=Disconnected
- `/TemperatureType` - 2 (generic)
- `/CustomName` - "Buffer Top"
- `/DeviceInstance` - 100 (default)

### Buffer Bottom Temperature
Service: `com.victronenergy.temperature.froeling_buffer_bottom`

- `/Temperature` - Temperature in °C
- `/Status` - 0=Ok, 1=Disconnected
- `/TemperatureType` - 2 (generic)
- `/CustomName` - "Buffer Bottom"
- `/DeviceInstance` - 101 (default)

### Boiler Status
Service: `com.victronenergy.generic.froeling_status`

- `/SystemStatus` - Text: "Automatic", "Off", "Domestic Hot Water", etc.
- `/SystemStatusCode` - Numeric code (0-8)
- `/FurnaceStatus` - Text: "Heating", "Furnace Off", "Ignition", etc.
- `/FurnaceStatusCode` - Numeric code (0-19)
- `/BoilerOperating` - Boolean: 1=operating, 0=not operating
- `/Connected` - Connection state
- `/DeviceInstance` - 102 (default)

## MQTT Integration

All dbus values are automatically published to MQTT by Venus OS if MQTT is enabled.

Topics follow the standard Venus OS pattern:
```
N/<portal-id>/temperature/<instance>/Temperature
N/<portal-id>/temperature/<instance>/Status
N/<portal-id>/generic/<instance>/SystemStatus
N/<portal-id>/generic/<instance>/FurnaceStatus
N/<portal-id>/generic/<instance>/BoilerOperating
```

### Example: Using Boiler Status in Node-RED

```javascript
// Subscribe to boiler operating status
msg.topic = "N/+/generic/102/BoilerOperating";

// Check if boiler is running
if (msg.payload == "1") {
    // Boiler is operating
    msg.payload = "Boiler is heating";
} else {
    // Boiler is not operating
    msg.payload = "Boiler is off";
}
return msg;
```

## VRM Portal

Temperature sensors appear automatically in VRM portal under "Temperatures".

To see boiler status in VRM:
1. Go to Settings → VRM online portal → Show
2. Enable "Generic" device types

## Troubleshooting

### Service won't start

Check logs:
```bash
tail -f /var/log/dbus-froeling/current
```

Check service status:
```bash
svstat /service/dbus-froeling
```

### Can't connect to Froeling

Test connection manually:
```bash
# Install mbpoll if not present
opkg update && opkg install mbpoll

# Test reading buffer top temperature (register 2000)
mbpoll 192.168.1.245 -p 502 -a 2 -t 3 -r 2000 -c 1
```

### Temperature shows as disconnected

Check:
1. Froeling IP address is correct in config.env
2. Modbus TCP is enabled on Froeling
3. No firewall blocking port 502
4. Device ID is correct (usually 2)

### Service stops after Venus OS reboot

Check `/data/rc.local` contains:
```bash
ln -sf /data/etc/dbus-froeling/service /service/dbus-froeling
```

## Status Codes Reference

### System Status Codes
- 0: Continuous Load
- 1: Domestic Hot Water
- 2: Automatic
- 3: Firewood Operation
- 4: Cleaning
- 5: Off
- 6: Extra Heating
- 7: Chimney Sweep
- 8: Cleaning

### Furnace Status Codes
- 0: FAULT
- 1: Furnace Off
- 2: Heating Up
- 3: Heating
- 4: Fire Maintenance
- 5: Fire Off
- 6: Door Open
- 7: Preparation
- 8: Pre-heating
- 9: Ignition
- 19: Ready

### Boiler Operating Logic

The `/BoilerOperating` boolean is true (1) when furnace status is **2-9** (any active/non-idle state):
- 2: Heating Up
- 3: Heating
- 4: Fire Maintenance
- 5: Fire Off
- 6: Door Open
- 7: Preparation
- 8: Pre-heating
- 9: Ignition

Only **0 (FAULT)** and **1 (Furnace Off)** are considered not operating (0).

This means the boiler is considered "operating" whenever it's doing anything other than being completely off or in a fault state.

## Files

- `dbus-froeling.py` - Main service script
- `install.sh` - Installation script
- `config.env` - Configuration file (created during install)
- `service/run` - Daemontools run script
- `service/log/run` - Daemontools log script

## Based On

This implementation follows patterns from:
- **dbus-imt-si-rs485tc** - Official Victron temperature sensor (Python)
- **mr-manuel/venus-os_dbus-mqtt-temperature** - Community best practices
- **velib_python** - Victron's official Python library

## License

This is custom integration code. Use at your own risk.

Victron Energy libraries (velib_python) are copyright Victron Energy.

## Support

For issues specific to this integration, check:
1. Service logs: `/var/log/dbus-froeling/current`
2. Dbus values: `dbus-spy` on Venus OS
3. MQTT topics: Use MQTT explorer

For Froeling-specific questions, consult your Froeling documentation or support.
