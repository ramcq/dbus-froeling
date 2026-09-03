#!/usr/bin/env python3
"""
dbus-froeling - Venus OS service for Froeling T4e pellet boiler
Publishes buffer tank temperatures and boiler status via dbus

Based on: 
- dbus-modbus-client (official Victron modbus client structure)
- dbus-imt-si-rs485tc (official Victron temperature sensor)
- mr-manuel/venus-os_dbus-mqtt-temperature (community best practices)
"""

import sys
import os
import logging
import time
from functools import partial

# Pymodbus 2.5.3 compatibility (Venus OS default version)
try:
    from pymodbus.client.sync import ModbusTcpClient
except ImportError:
    # Fallback for newer pymodbus versions
    from pymodbus.client import ModbusTcpClient

# Victron packages
sys.path.insert(1, os.path.join(os.path.dirname(__file__), './ext/velib_python'))
from vedbus import VeDbusService
from settingsdevice import SettingsDevice
from gi.repository import GLib
from dbus.mainloop.glib import DBusGMainLoop
import dbus

def private_bus():
    """Create a private dbus connection for each service"""
    return dbus.SessionBus(private=True) if 'DBUS_SESSION_BUS_ADDRESS' in os.environ else dbus.SystemBus(private=True)

# Configuration
FROELING_HOST = os.environ.get('FROELING_HOST', '192.168.1.245')
FROELING_PORT = int(os.environ.get('FROELING_PORT', '502'))
FROELING_DEVICE_ID = int(os.environ.get('FROELING_DEVICE_ID', '2'))
UPDATE_INTERVAL = int(os.environ.get('UPDATE_INTERVAL', '10000'))  # milliseconds (10 seconds)

# Modbus register definitions (offsets from 30001)
BOILER_FLOW_TEMP = 0        # Register 30001: Boiler flow temperature (°C * 2)
BUFFER_TEMP_TOP = 2000      # Register 32001: Buffer top temperature (°C * 2)
BUFFER_TEMP_BOTTOM = 2002   # Register 32003: Buffer bottom temperature (°C * 2)
SYSTEM_STATUS = 4000        # Register 34001: System operating status
FURNACE_STATUS = 4001       # Register 34002: Furnace/boiler status

# Modbus discrete input definitions (offsets from 10001, read with FC 02)
# Only 10001-10004 exist; offset 4 and up return exception 2 (illegal data address)
BOILER_RELEASE = 3          # Input 10004: Kesselfreigabe (KM-14 external release contact)

# Seconds to wait for localsettings to appear. SettingsDevice raises immediately with
# the default of 0, which loses the race if this service starts first at boot.
SETTINGS_TIMEOUT = 10

# Digital input /State text, from dbus-digitalinputs: /State = 2 * translation + level.
# Indexed by translation, then by level.
DIGITAL_INPUT_TRANSLATIONS = [
    ('Low', 'High'),
    ('Off', 'On'),
    ('No', 'Yes'),
    ('Open', 'Closed'),
    ('OK', 'Alarm'),
    ('Running', 'Stopped'),
]

# Status mappings
SYSTEM_STATUS_MAP = {
    0: "Continuous Load",
    1: "Domestic Hot Water",
    2: "Automatic",
    3: "Firewood Operation",
    4: "Cleaning",
    5: "Off",
    6: "Extra Heating",
    7: "Chimney Sweep",
    8: "Cleaning"
}

FURNACE_STATUS_MAP = {
    0: "FAULT",
    1: "Furnace Off",
    2: "Heating Up",
    3: "Heating",
    4: "Fire Maintenance",
    5: "Fire Off",
    6: "Door Open",
    7: "Preparation",
    8: "Pre-heating",
    9: "Ignition",
    10: "Shutdown Wait",
    11: "Shutdown Wait 1",
    12: "Shutdown Feed 1",
    13: "Shutdown Wait 2",
    14: "Shutdown Feed 2",
    15: "Cleaning",
    16: "Wait 2h",
    17: "Suction Heating",
    18: "Ignition Fault",
    19: "Ready",
    20: "Close Grate",
    21: "Empty Stoker",
    22: "Pre-heat",
    23: "Suction",
    24: "Close RSE",
    25: "Open RSE",
    26: "Tip Grate",
    27: "Pre-heating Ignition",
    28: "Residual Feed",
    29: "Fill Stoker",
    30: "Heat Lambda Probe",
    31: "Fan Run-on I",
    32: "Fan Run-on II",
    33: "Shut Down",
    34: "Re-ignition",
    35: "Ignition Wait",
    36: "FB: Close RSE",
    37: "FB: Ventilate Boiler",
    38: "FB: Ignition",
    39: "FB: Min Feed",
    40: "Close RSE",
    41: "FAULT: STB/NA",
    42: "FAULT: Tipping Grate",
    43: "FAULT: FR Overpressure",
    44: "FAULT: Door Contact",
    45: "FAULT: Induced Draft",
    46: "FAULT: Environment",
    47: "ERROR: STB/NA",
    48: "ERROR: Tipping Grate",
    49: "ERROR: FR Overpressure",
    50: "ERROR: Door Contact",
    51: "ERROR: Induced Draft",
    52: "ERROR: Environment",
    53: "ERROR: Stoker",
    54: "FAULT: Stoker",
    55: "FB: Empty Stoker",
    56: "Pre-ventilation",
    57: "FAULT: Wood Chips",
    58: "ERROR: Wood Chips",
    59: "AB: Door Open",
    60: "AB: Heating Up",
    61: "AB: Heating",
    62: "ERROR: STB/NA",
    63: "ERROR: General",
    64: "AB: Fire Off",
    65: "Self-test Active",
    66: "Error Remedy 20min",
    67: "ERROR: Drop Shaft",
    68: "FAULT: Drop Shaft",
    69: "Cleaning Possible",
    70: "Heating - Cleaning",
    71: "LW Heating Up",
    72: "LW Heating",
    73: "LW Heat/Shutdown",
    74: "FAULT Safe",
    75: "AGR Run-on",
    76: "AGR Cleaning",
    77: "Ignition OFF",
    78: "Filter Cleaning",
    79: "Heating Assistant",
    80: "LW Ignition",
    81: "LW Fault",
    82: "Sensor Check"
}

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dbus-froeling")


class TemperatureSensor:
    """Represents a single temperature sensor device on dbus"""
    
    def __init__(self, servicename, settingspath, default_instance, productname, customname):
        self.servicename = servicename
        self.productname = productname
        self.customname = customname
        
        # Create the dbus service with private bus and register=False
        self.dbusservice = VeDbusService(servicename, bus=private_bus(), register=False)
        
        # Create settings for device instance (format: class:instance)
        self.settings = SettingsDevice(
            bus=self.dbusservice._dbusconn,
            supportedSettings={
                'instance': [settingspath, f'temperature:{default_instance}', 0, 0],
            },
            eventCallback=None,
            timeout=SETTINGS_TIMEOUT
        )
        
        # Parse the device instance from settings (format is class:instance)
        class_and_instance = self.settings['instance']
        deviceinstance = int(class_and_instance.split(':')[1])
        
        # Mandatory paths for all services
        self.dbusservice.add_path('/Mgmt/ProcessName', __file__)
        self.dbusservice.add_path('/Mgmt/ProcessVersion', '1.0.0')
        self.dbusservice.add_path('/Mgmt/Connection', f'{FROELING_HOST}:{FROELING_PORT}')
        self.dbusservice.add_path('/DeviceInstance', deviceinstance)
        self.dbusservice.add_path('/ProductId', 0xFFFF)
        self.dbusservice.add_path('/ProductName', productname)
        self.dbusservice.add_path('/FirmwareVersion', '1.0.0')
        self.dbusservice.add_path('/HardwareVersion', 'T4e')
        self.dbusservice.add_path('/Connected', 1)
        
        # Temperature sensor specific paths
        self.dbusservice.add_path('/Temperature', None, gettextcallback=lambda p, v: f"{v:.1f}°C" if v is not None else "---")
        self.dbusservice.add_path('/Status', 1)  # 0=Ok, 1=Disconnected
        self.dbusservice.add_path('/TemperatureType', 2)  # 2=generic
        self.dbusservice.add_path('/CustomName', customname)
        
        # Now register the service after all paths are added
        self.dbusservice.register()
        
        logger.info(f"Created temperature sensor: {servicename} (instance {deviceinstance})")
    
    def update(self, temperature):
        """Update the temperature value"""
        if temperature is not None:
            self.dbusservice['/Temperature'] = temperature
            self.dbusservice['/Status'] = 0  # Ok
            self.dbusservice['/Connected'] = 1
        else:
            self.dbusservice['/Status'] = 1  # Disconnected
            self.dbusservice['/Connected'] = 0


class DigitalInput:
    """Base class for a Victron digital input service.

    Mirrors the path set and state arithmetic of Victron's own dbus-digitalinputs
    PinAlarm, so that the GX GUI, the Venus Modbus TCP server and VRM all see the
    shape they expect.

    Subclasses set TYPE_ID and TRANSLATION, optionally override _add_device_paths()
    to publish their own paths, and call _apply() with the raw input level.

    Note the level convention, which follows dbus-digitalinputs: /State is
    2 * TRANSLATION + level, so for TRANSLATION 5 (Running/Stopped) it is level 0
    that means "Running", not level 1.
    """

    TYPE_ID = 0
    TRANSLATION = 0
    PRODUCT_ID = 0xA166   # dbus-digitalinputs PinAlarm.product_id

    def __init__(self, servicename, settingspath, default_instance, productname, customname):
        self.servicename = servicename
        self.productname = productname
        self.customname = customname
        self._level = None

        self.dbusservice = VeDbusService(servicename, bus=private_bus(), register=False)

        # Per-device settings live alongside the instance setting, e.g.
        # /Settings/Devices/froeling_release/{ClassAndVrmInstance,InvertTranslation,...}
        prefix = settingspath.rsplit('/', 1)[0]
        self.settings = SettingsDevice(
            bus=self.dbusservice._dbusconn,
            supportedSettings={
                'instance': [settingspath, f'digitalinput:{default_instance}', 0, 0],
                'AlarmSetting': [f'{prefix}/AlarmSetting', 0, 0, 1],
                'InvertTranslation': [f'{prefix}/InvertTranslation', 0, 0, 1],
                'InvertAlarm': [f'{prefix}/InvertAlarm', 0, 0, 1],
                'name': [f'{prefix}/CustomName', customname, '', ''],
            },
            eventCallback=self._setting_changed,
            timeout=SETTINGS_TIMEOUT
        )

        # Parse the device instance from settings (format is class:instance)
        class_and_instance = self.settings['instance']
        deviceinstance = int(class_and_instance.split(':')[1])

        # Mandatory paths
        self.dbusservice.add_path('/Mgmt/ProcessName', __file__)
        self.dbusservice.add_path('/Mgmt/ProcessVersion', '1.0.0')
        self.dbusservice.add_path('/Mgmt/Connection', f'{FROELING_HOST}:{FROELING_PORT}')
        self.dbusservice.add_path('/DeviceInstance', deviceinstance)
        self.dbusservice.add_path('/ProductId', self.PRODUCT_ID)
        self.dbusservice.add_path('/ProductName', productname)
        self.dbusservice.add_path('/FirmwareVersion', '1.0.0')
        self.dbusservice.add_path('/HardwareVersion', 'T4e')
        self.dbusservice.add_path('/Connected', 1)

        # Digital input paths, in the order dbus-digitalinputs creates them.
        # /InputState and /State stay invalid until the first successful read: publishing
        # a placeholder level asserts a state we have not measured, and subscribers see
        # that placeholder correct itself one poll later as a real edge.
        self.dbusservice.add_path('/InputState', None, writeable=False)
        self.dbusservice.add_path('/State', None, writeable=False,
                                   gettextcallback=self._state_text)
        self.dbusservice.add_path('/Alarm', 0, writeable=False)
        self.dbusservice.add_path('/Type', self.TYPE_ID, writeable=False)
        self.dbusservice.add_path('/Count', 0, writeable=False)
        self.dbusservice.add_path('/CustomName', self.settings['name'], writeable=True,
                                   onchangecallback=partial(self._change_setting, 'name'))

        # Mirror the settings onto the service, as the GX GUI's digital input setup
        # page binds ListSwitch items to these three paths for every input type.
        for name in ('AlarmSetting', 'InvertTranslation', 'InvertAlarm'):
            self.dbusservice.add_path(f'/Settings/{name}', self.settings[name],
                                       writeable=True,
                                       onchangecallback=partial(self._change_setting, name))

        # Let subclasses add their own paths before the service is registered
        self._add_device_paths()

        self.dbusservice.register()

        logger.info(f"Created {type(self).__name__}: {servicename} (instance {deviceinstance})")

    def _add_device_paths(self):
        """Hook for subclasses to publish additional paths before registration"""
        pass

    def _change_setting(self, name, path, value):
        self.settings[name] = value
        return True

    def _setting_changed(self, name, old, new):
        """Re-evaluate the published state when a setting is changed elsewhere"""
        # This fires when an attribute of a setting changes too, not just the
        # value, so bail if the value is unchanged.
        if old == new:
            return

        if name == 'name':
            self.dbusservice['/CustomName'] = new
        elif name in ('AlarmSetting', 'InvertTranslation', 'InvertAlarm'):
            self.dbusservice[f'/Settings/{name}'] = new
            if self._level is not None:
                self._publish(self._level)

    def _state_text(self, path, value):
        """GetText for /State, which is invalid until the first read"""
        if value is None:
            return ''
        return DIGITAL_INPUT_TRANSLATIONS[value // 2][value % 2]

    def _state_for(self, level):
        return 2 * self.TRANSLATION + (level ^ self.settings['InvertTranslation'])

    def _alarm_for(self, level):
        return 2 * bool((level ^ self.settings['InvertAlarm']) and self.settings['AlarmSetting'])

    def _publish(self, level):
        self.dbusservice['/InputState'] = level
        self.dbusservice['/State'] = self._state_for(level)
        self.dbusservice['/Alarm'] = self._alarm_for(level)

    def _apply(self, level):
        """Publish a new input level"""
        self._level = level
        self._publish(level)
        self.dbusservice['/Connected'] = 1

    def set_connected(self, connected):
        self.dbusservice['/Connected'] = 1 if connected else 0


class BoilerOperatingContact(DigitalInput):
    """The boiler's operating state as a digital input, plus its status information.

    Type 9 (Generator) uses the Running/Stopped translation, in which level 0 is
    "Running" — so the level published here is the inverse of "operating".
    """

    TYPE_ID = 9
    TRANSLATION = 5   # Running, Stopped

    # All error and fault conditions
    FAULT_STATES = {
        0,            # FAULT
        18,           # Ignition Fault
        41, 42, 43, 44, 45, 46,  # FAULT: STB/NA, Tipping Grate, FR Overpressure, Door Contact, Induced Draft, Environment
        47, 48, 49, 50, 51, 52, 53, 54,  # ERROR: STB/NA, Tipping Grate, FR Overpressure, Door Contact, Induced Draft, Environment, Stoker, FAULT: Stoker
        57, 58,       # FAULT: Wood Chips, ERROR: Wood Chips
        62, 63,       # ERROR: STB/NA, ERROR: General
        66,           # Error Remedy 20min
        67, 68,       # ERROR: Drop Shaft, FAULT: Drop Shaft
        74,           # FAULT Safe
        81            # LW Fault
    }

    # Definitely not operating (off, ready, waiting states)
    IDLE_STATES = {
        1,            # Furnace Off
        5,            # Fire Off
        16,           # Wait 2h
        19,           # Ready
        33,           # Shut Down
        64,           # AB: Fire Off
        77            # Ignition OFF
    }

    def _add_device_paths(self):
        self.dbusservice.add_path('/SystemStatus', None, writeable=False)
        self.dbusservice.add_path('/SystemStatusCode', None, writeable=False)
        self.dbusservice.add_path('/FurnaceStatus', None, writeable=False)
        self.dbusservice.add_path('/FurnaceStatusCode', None, writeable=False)

    def update(self, system_status_code, furnace_status_code):
        """Update the digital input state and boiler status based on furnace status"""
        if system_status_code is not None:
            self.dbusservice['/SystemStatus'] = SYSTEM_STATUS_MAP.get(
                system_status_code, f"Unknown ({system_status_code})")
            self.dbusservice['/SystemStatusCode'] = system_status_code
            self.dbusservice['/Connected'] = 1
        else:
            self.dbusservice['/Connected'] = 0

        if furnace_status_code is None:
            # Read failed. Hold the last known state rather than asserting "stopped":
            # a transient Modbus error would otherwise show subscribers the boiler
            # stopping and restarting, which reads as an ignition. /Connected says the
            # value is stale.
            self.dbusservice['/Connected'] = 0
            return

        self.dbusservice['/FurnaceStatus'] = FURNACE_STATUS_MAP.get(
            furnace_status_code, f"Unknown ({furnace_status_code})")
        self.dbusservice['/FurnaceStatusCode'] = furnace_status_code

        # Conservative status categorization: NOT fault and NOT idle = operating.
        # This includes all startup sequences (tip grate, filling, ignition, etc.),
        # shutdown sequences with active feeding, cleaning cycles, etc.
        operating = (furnace_status_code not in self.FAULT_STATES
                     and furnace_status_code not in self.IDLE_STATES)

        # Level 0 is "Running" for the Generator translation
        self._apply(0 if operating else 1)


class BoilerReleaseContact(DigitalInput):
    """Kesselfreigabe (KM-14 external release contact) as a digital input.

    Type 3 (Bilge pump) uses the Off/On translation, so /State is the conventional
    2/3 pair rather than a mismatched type/state combination.

    Measured polarity: bit 0 = contact open (release withheld),
                       bit 1 = contact closed (release granted).
    """

    TYPE_ID = 3
    TRANSLATION = 1   # Off, On

    def update(self, released):
        """Update from the Kesselfreigabe discrete input (None = read failed)"""
        if released is None:
            self.dbusservice['/Connected'] = 0
            return

        self._apply(1 if released else 0)



class FroelingMonitor:
    """Main monitor class that polls Froeling and updates devices"""
    
    def __init__(self):
        self.modbus_client = None
        
        # Connect to Froeling
        self.connect_modbus()
        
        # Create device instances with settings support
        self.buffer_top = TemperatureSensor(
            'com.victronenergy.temperature.froeling_buffer_top',
            '/Settings/Devices/froeling_buffer_top/ClassAndVrmInstance',
            100,
            'Froeling Buffer Top',
            'Buffer Top'
        )
        
        self.buffer_bottom = TemperatureSensor(
            'com.victronenergy.temperature.froeling_buffer_bottom',
            '/Settings/Devices/froeling_buffer_bottom/ClassAndVrmInstance',
            101,
            'Froeling Buffer Bottom',
            'Buffer Bottom'
        )

        self.boiler_flow = TemperatureSensor(
            'com.victronenergy.temperature.froeling_boiler_flow',
            '/Settings/Devices/froeling_boiler_flow/ClassAndVrmInstance',
            103,
            'Froeling Boiler Flow',
            'Boiler Flow'
        )

        self.operating_contact = BoilerOperatingContact(
            'com.victronenergy.digitalinput.froeling_operating',
            '/Settings/Devices/froeling_operating/ClassAndVrmInstance',
            102,
            'Froeling Operating Contact',
            'Boiler Operating'
        )

        self.release_contact = BoilerReleaseContact(
            'com.victronenergy.digitalinput.froeling_release',
            '/Settings/Devices/froeling_release/ClassAndVrmInstance',
            104,
            'Froeling Boiler Release',
            'Boiler Release'
        )

        # Start update timer
        GLib.timeout_add(UPDATE_INTERVAL, self.update)

        logger.info(f"FroelingMonitor started, polling every {UPDATE_INTERVAL}ms")

    def connect_modbus(self):
        """Connect to Froeling modbus TCP"""
        try:
            self.modbus_client = ModbusTcpClient(
                FROELING_HOST, 
                port=FROELING_PORT
            )
            if self.modbus_client.connect():
                logger.info(f"Connected to Froeling at {FROELING_HOST}:{FROELING_PORT}")
            else:
                logger.error(f"Failed to connect to Froeling at {FROELING_HOST}:{FROELING_PORT}")
                self.modbus_client = None
        except Exception as e:
            logger.error(f"Error connecting to Froeling: {e}")
            self.modbus_client = None
    
    def read_temperature(self, register):
        """Read temperature from register (value is in °C * 2)"""
        if not self.modbus_client:
            return None
        
        try:
            result = self.modbus_client.read_input_registers(
                register, 
                count=1, 
                unit=FROELING_DEVICE_ID
            )
            
            if not result.isError() and hasattr(result, 'registers'):
                raw_value = result.registers[0]
                # Convert from °C * 2 to actual °C
                temp_c = raw_value / 2.0
                return temp_c
            else:
                logger.warning(f"Error reading temperature register {register}")
                return None
                
        except Exception as e:
            logger.error(f"Exception reading temperature register {register}: {e}")
            return None
    
    def read_status(self, register):
        """Read status value from register"""
        if not self.modbus_client:
            return None
        
        try:
            result = self.modbus_client.read_input_registers(
                register,
                count=1,
                unit=FROELING_DEVICE_ID
            )
            
            if not result.isError() and hasattr(result, 'registers'):
                return result.registers[0]
            else:
                logger.warning(f"Error reading status register {register}")
                return None
                
        except Exception as e:
            logger.error(f"Exception reading status register {register}: {e}")
            return None
    
    def read_discrete_input(self, offset):
        """Read a discrete input with FC 02 (offsets from 10001)"""
        if not self.modbus_client:
            return None

        try:
            result = self.modbus_client.read_discrete_inputs(
                offset,
                count=1,
                unit=FROELING_DEVICE_ID
            )

            if not result.isError() and hasattr(result, 'bits'):
                return bool(result.bits[0])
            else:
                logger.warning(f"Error reading discrete input {offset}")
                return None

        except Exception as e:
            logger.error(f"Exception reading discrete input {offset}: {e}")
            return None

    def update(self):
        """Update all sensor values from Froeling"""
        
        # Reconnect if disconnected
        if not self.modbus_client or not self.modbus_client.is_socket_open():
            logger.warning("Modbus connection lost, reconnecting...")
            self.connect_modbus()
            if not self.modbus_client:
                # Mark all devices as disconnected
                self.buffer_top.update(None)
                self.buffer_bottom.update(None)
                self.boiler_flow.update(None)
                self.operating_contact.update(None, None)
                self.release_contact.update(None)
                return True

        try:
            # Read buffer tank and boiler flow temperatures
            temp_top = self.read_temperature(BUFFER_TEMP_TOP)
            temp_bottom = self.read_temperature(BUFFER_TEMP_BOTTOM)
            temp_flow = self.read_temperature(BOILER_FLOW_TEMP)

            # Update temperature sensors
            self.buffer_top.update(temp_top)
            self.buffer_bottom.update(temp_bottom)
            self.boiler_flow.update(temp_flow)

            # Read boiler status
            system_status_code = self.read_status(SYSTEM_STATUS)
            furnace_status_code = self.read_status(FURNACE_STATUS)

            # Update operating contact (includes all status information)
            self.operating_contact.update(system_status_code, furnace_status_code)

            # Read and publish the Kesselfreigabe external release contact
            released = self.read_discrete_input(BOILER_RELEASE)
            self.release_contact.update(released)

            logger.debug(f"Updated: Top={temp_top}°C, Bottom={temp_bottom}°C, "
                        f"Flow={temp_flow}°C, "
                        f"System={system_status_code}, Furnace={furnace_status_code}, "
                        f"Release={released}")

        except Exception as e:
            logger.error(f"Error updating values: {e}")
            # Mark devices as disconnected on error
            self.buffer_top.update(None)
            self.buffer_bottom.update(None)
            self.boiler_flow.update(None)
            self.operating_contact.update(None, None)
            self.release_contact.update(None)
        
        return True  # Keep timer running


def main():
    """Main entry point"""
    try:
        # Initialize dbus main loop
        DBusGMainLoop(set_as_default=True)
        
        # Create monitor instance
        monitor = FroelingMonitor()
        
        # Start GLib main loop
        mainloop = GLib.MainLoop()
        mainloop.run()
        
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
