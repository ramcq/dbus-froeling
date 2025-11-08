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
  - Digital input contact: Boiler Operating (running/stopped)
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
- **Note**: Compatible with pymodbus 2.5.3 (included in Venus OS) and newer versions

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
FROELING_HOST=192.168.1.245    # IP address of your Froeling
FROELING_PORT=502               # Modbus TCP port (standard Modbus port)
FROELING_DEVICE_ID=2            # Modbus device/slave ID (default 2)
UPDATE_INTERVAL=10000           # Update interval in milliseconds (10 seconds)
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

### Boiler Operating Contact (Digital Input)
Service: `com.victronenergy.digitalinput.froeling_operating`

**Digital Input Paths:**
- `/State` - 10=running, 11=stopped (with text callback: "Running"/"Stopped")
- `/Type` - 9 (Generator)
- `/Alarm` - 0 (no alarm)
- `/Count` - Pulse counter (not used)
- `/CustomName` - "Boiler Operating"

**Boiler Status Paths:**
- `/SystemStatus` - Text: "Automatic", "Off", "Domestic Hot Water", etc.
- `/SystemStatusCode` - Numeric code (0-8)
- `/FurnaceStatus` - Text: "Heating", "Furnace Off", "Ignition", etc.
- `/FurnaceStatusCode` - Numeric code (0-19)

**Common Paths:**
- `/Connected` - Connection state
- `/DeviceInstance` - 102 (default)

## MQTT Integration

All dbus values are automatically published to MQTT by Venus OS if MQTT is enabled.

Topics follow the standard Venus OS pattern:
```
N/<portal-id>/temperature/<instance>/Temperature
N/<portal-id>/temperature/<instance>/Status
N/<portal-id>/digitalinput/102/State
N/<portal-id>/digitalinput/102/SystemStatus
N/<portal-id>/digitalinput/102/FurnaceStatus
```

### Example: Using Boiler Status in Node-RED

```javascript
// Subscribe to boiler operating status (digital input state)
msg.topic = "N/+/digitalinput/102/State";

// Check if boiler is running
if (msg.payload == "10") {
    // Boiler is running (State=10)
    msg.payload = "Boiler is heating";
} else if (msg.payload == "11") {
    // Boiler is stopped (State=11)
    msg.payload = "Boiler is off";
}
return msg;
```

You can also subscribe to detailed furnace status:
```javascript
// Subscribe to detailed furnace status
msg.topic = "N/+/digitalinput/102/FurnaceStatus";
// Returns text like: "Heating", "Ignition", "Furnace Off", etc.
```

## VRM Portal

Temperature sensors appear automatically in VRM portal under "Temperatures".

To see boiler operating status in VRM:
1. Go to Settings → VRM online portal → Show
2. Enable "Digital Input" device types

The boiler operating contact will appear as a digital input showing "Running" or "Stopped" state, along with detailed system and furnace status information.

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
- 10: Shutdown Wait
- 11: Shutdown Wait 1
- 12: Shutdown Feed 1
- 13: Shutdown Wait 2
- 14: Shutdown Feed 2
- 15: Cleaning
- 16: Wait 2h
- 17: Suction Heating
- 18: Ignition Fault
- 19: Ready

### Boiler Operating Logic

The digital input `/State` is **10 (running)** when furnace status is **2-17** (any active/non-idle state):
- 2: Heating Up
- 3: Heating
- 4: Fire Maintenance
- 5: Fire Off
- 6: Door Open
- 7: Preparation
- 8: Pre-heating
- 9: Ignition
- 10: Shutdown Wait
- 11: Shutdown Wait 1
- 12: Shutdown Feed 1
- 13: Shutdown Wait 2
- 14: Shutdown Feed 2
- 15: Cleaning
- 16: Wait 2h
- 17: Suction Heating

Only **0 (FAULT)**, **1 (Furnace Off)**, **18 (Ignition Fault)**, and **19 (Ready/Standby)** are considered not operating (State = **11 (stopped)**).

This means the boiler is considered "running" (State=10) whenever it's doing anything - heating, shutting down, cleaning, etc. - only complete shutdown, standby, or fault states are considered "stopped" (State=11).

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
