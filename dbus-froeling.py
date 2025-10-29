#!/usr/bin/env python3
"""
dbus-froeling - Venus OS service for Froeling T4e pellet boiler
Publishes buffer tank temperatures and boiler status via dbus

Based on: 
- dbus-imt-si-rs485tc (official Victron temperature sensor)
- mr-manuel/venus-os_dbus-mqtt-temperature (community best practices)
"""

import sys
import os
import logging
import time

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

# Configuration
FROELING_HOST = os.environ.get('FROELING_HOST', '192.168.1.245')
FROELING_PORT = int(os.environ.get('FROELING_PORT', '502'))
FROELING_DEVICE_ID = int(os.environ.get('FROELING_DEVICE_ID', '2'))
UPDATE_INTERVAL = int(os.environ.get('UPDATE_INTERVAL', '10000'))  # milliseconds (10 seconds)

# Modbus register definitions (offsets from 30001)
BUFFER_TEMP_TOP = 2000      # Register 32001: Buffer top temperature (°C * 2)
BUFFER_TEMP_BOTTOM = 2002   # Register 32003: Buffer bottom temperature (°C * 2)
SYSTEM_STATUS = 4000        # Register 34001: System operating status
FURNACE_STATUS = 4001       # Register 34002: Furnace/boiler status

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
    19: "Ready"
}

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dbus-froeling")


class FroelingMonitor:
    def __init__(self):
        self.modbus_client = None
        self.services = {}
        self.last_update = 0
        
        # Connect to Froeling
        self.connect_modbus()
        
        # Create dbus services for buffer tank temperatures
        self.create_temperature_services()
        
        # Create dbus service for boiler status
        self.create_status_service()
        
        # Start update timer
        GLib.timeout_add(UPDATE_INTERVAL, self.update)
        
        logger.info(f"dbus-froeling started, monitoring {FROELING_HOST}:{FROELING_PORT}")
    
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
    
    def create_temperature_services(self):
        """Create dbus services for buffer tank top and bottom temperatures"""
        
        # Buffer Top Temperature
        servicename = 'com.victronenergy.temperature.froeling_buffer_top'
        self.services['buffer_top'] = VeDbusService(servicename)
        service = self.services['buffer_top']
        
        # Create device instance for Settings
        settings = SettingsDevice(
            bus=service._dbusconn,
            supportedSettings={
                'instance': ['/Settings/Devices/froeling_buffer_top/ClassAndVrmInstance', 100, 0, 255],
            },
            eventCallback=None
        )
        
        # Mandatory paths for all services
        service.add_path('/Mgmt/ProcessName', __file__)
        service.add_path('/Mgmt/ProcessVersion', '1.0.0')
        service.add_path('/Mgmt/Connection', f'{FROELING_HOST}:{FROELING_PORT}')
        service.add_path('/DeviceInstance', settings.get_value('instance'))
        service.add_path('/ProductId', 0xFFFF)  # Generic product ID for custom service
        service.add_path('/ProductName', 'Froeling Buffer Top')
        service.add_path('/FirmwareVersion', '1.0.0')
        service.add_path('/HardwareVersion', 'T4e')
        service.add_path('/Connected', 1)
        
        # Temperature sensor specific paths
        service.add_path('/Temperature', None, gettextcallback=lambda p, v: f"{v:.1f}°C" if v is not None else "---")
        service.add_path('/Status', 1)  # 0=Ok, 1=Disconnected, 2=Short, 3=Reverse polarity, 4=Unknown
        service.add_path('/TemperatureType', 2)  # 0=battery, 1=fridge, 2=generic
        service.add_path('/CustomName', 'Buffer Top')
        
        logger.info(f"Created service: {servicename} on device instance {settings.get_value('instance')}")
        
        # Buffer Bottom Temperature
        servicename = 'com.victronenergy.temperature.froeling_buffer_bottom'
        self.services['buffer_bottom'] = VeDbusService(servicename)
        service = self.services['buffer_bottom']
        
        settings = SettingsDevice(
            bus=service._dbusconn,
            supportedSettings={
                'instance': ['/Settings/Devices/froeling_buffer_bottom/ClassAndVrmInstance', 101, 0, 255],
            },
            eventCallback=None
        )
        
        service.add_path('/Mgmt/ProcessName', __file__)
        service.add_path('/Mgmt/ProcessVersion', '1.0.0')
        service.add_path('/Mgmt/Connection', f'{FROELING_HOST}:{FROELING_PORT}')
        service.add_path('/DeviceInstance', settings.get_value('instance'))
        service.add_path('/ProductId', 0xFFFF)
        service.add_path('/ProductName', 'Froeling Buffer Bottom')
        service.add_path('/FirmwareVersion', '1.0.0')
        service.add_path('/HardwareVersion', 'T4e')
        service.add_path('/Connected', 1)
        
        service.add_path('/Temperature', None, gettextcallback=lambda p, v: f"{v:.1f}°C" if v is not None else "---")
        service.add_path('/Status', 1)
        service.add_path('/TemperatureType', 2)
        service.add_path('/CustomName', 'Buffer Bottom')
        
        logger.info(f"Created service: {servicename} on device instance {settings.get_value('instance')}")
    
    def create_status_service(self):
        """Create dbus service for boiler status"""
        
        servicename = 'com.victronenergy.generic.froeling_status'
        self.services['status'] = VeDbusService(servicename)
        service = self.services['status']
        
        settings = SettingsDevice(
            bus=service._dbusconn,
            supportedSettings={
                'instance': ['/Settings/Devices/froeling_status/ClassAndVrmInstance', 102, 0, 255],
            },
            eventCallback=None
        )
        
        # Mandatory paths
        service.add_path('/Mgmt/ProcessName', __file__)
        service.add_path('/Mgmt/ProcessVersion', '1.0.0')
        service.add_path('/Mgmt/Connection', f'{FROELING_HOST}:{FROELING_PORT}')
        service.add_path('/DeviceInstance', settings.get_value('instance'))
        service.add_path('/ProductId', 0xFFFF)
        service.add_path('/ProductName', 'Froeling Status')
        service.add_path('/FirmwareVersion', '1.0.0')
        service.add_path('/HardwareVersion', 'T4e')
        service.add_path('/Connected', 1)
        
        # Custom status paths
        service.add_path('/SystemStatus', None, writeable=False)
        service.add_path('/SystemStatusCode', None, writeable=False)
        service.add_path('/FurnaceStatus', None, writeable=False)
        service.add_path('/FurnaceStatusCode', None, writeable=False)
        service.add_path('/BoilerOperating', 0, writeable=False)  # Boolean: 0=not operating, 1=operating
        
        logger.info(f"Created service: {servicename} on device instance {settings.get_value('instance')}")
    
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
    
    def update(self):
        """Update all sensor values from Froeling"""
        
        # Reconnect if disconnected
        if not self.modbus_client or not self.modbus_client.is_socket_open():
            logger.warning("Modbus connection lost, reconnecting...")
            self.connect_modbus()
            if not self.modbus_client:
                # Mark all services as disconnected
                for service_name, service in self.services.items():
                    if 'buffer' in service_name:
                        service['/Status'] = 1  # Disconnected
                    service['/Connected'] = 0
                return True
        
        try:
            # Read buffer tank temperatures
            temp_top = self.read_temperature(BUFFER_TEMP_TOP)
            temp_bottom = self.read_temperature(BUFFER_TEMP_BOTTOM)
            
            # Update buffer top service
            if temp_top is not None:
                self.services['buffer_top']['/Temperature'] = temp_top
                self.services['buffer_top']['/Status'] = 0  # Ok
                self.services['buffer_top']['/Connected'] = 1
            else:
                self.services['buffer_top']['/Status'] = 1  # Disconnected
                self.services['buffer_top']['/Connected'] = 0
            
            # Update buffer bottom service
            if temp_bottom is not None:
                self.services['buffer_bottom']['/Temperature'] = temp_bottom
                self.services['buffer_bottom']['/Status'] = 0  # Ok
                self.services['buffer_bottom']['/Connected'] = 1
            else:
                self.services['buffer_bottom']['/Status'] = 1  # Disconnected
                self.services['buffer_bottom']['/Connected'] = 0
            
            # Read boiler status
            system_status_code = self.read_status(SYSTEM_STATUS)
            furnace_status_code = self.read_status(FURNACE_STATUS)
            
            # Update status service
            if system_status_code is not None:
                system_status_text = SYSTEM_STATUS_MAP.get(system_status_code, f"Unknown ({system_status_code})")
                self.services['status']['/SystemStatus'] = system_status_text
                self.services['status']['/SystemStatusCode'] = system_status_code
                self.services['status']['/Connected'] = 1
            else:
                self.services['status']['/Connected'] = 0
            
            if furnace_status_code is not None:
                furnace_status_text = FURNACE_STATUS_MAP.get(furnace_status_code, f"Unknown ({furnace_status_code})")
                self.services['status']['/FurnaceStatus'] = furnace_status_text
                self.services['status']['/FurnaceStatusCode'] = furnace_status_code
                
                # Determine if boiler is operating (simplified boolean)
                # Consider "operating" for all active/non-idle states (2-17)
                # Only "FAULT" (0), "Furnace Off" (1), "Ignition Fault" (18), and "Ready" (19) are not operating
                operating = furnace_status_code >= 2 and furnace_status_code <= 17
                self.services['status']['/BoilerOperating'] = 1 if operating else 0
            
            logger.debug(f"Updated: Top={temp_top}°C, Bottom={temp_bottom}°C, "
                        f"System={system_status_code}, Furnace={furnace_status_code}")
            
        except Exception as e:
            logger.error(f"Error updating values: {e}")
            # Mark services as disconnected on error
            for service in self.services.values():
                service['/Connected'] = 0
        
        return True  # Keep timer running


def main():
    """Main entry point"""
    try:
        from dbus.mainloop.glib import DBusGMainLoop
        
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
