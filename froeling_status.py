#!/usr/bin/env python3
"""
Simple script to fetch buffer tank temperatures and operating status
from Froeling T4e pellet boiler via Modbus TCP
"""

try:
    from pymodbus.client.sync import ModbusTcpClient
except ImportError:
    # Fallback for newer pymodbus versions
    from pymodbus.client import ModbusTcpClient
import sys

# Configuration
HOST = "192.168.1.245"
PORT = 502
DEVICE_ID = 2

# Register definitions (based on Modbus address - 30001 offset for input registers)
BUFFER_TEMP_TOP = 2000      # Register 32001: Buffer top temperature
BUFFER_TEMP_BOTTOM = 2002   # Register 32003: Buffer bottom temperature
SYSTEM_STATUS = 4000        # Register 34001: System operating status
FURNACE_STATUS = 4001       # Register 34002: Furnace/boiler status

# Status mappings (from Home Assistant integration)
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
    19: "Ready"
}


def read_temperature(client, register):
    """Read temperature from register (value is in °C * 2)"""
    try:
        result = client.read_input_registers(register, count=1, slave=DEVICE_ID)
        if not result.isError():
            raw_value = result.registers[0]
            # Convert from °C * 2 to actual °C
            temp_c = raw_value / 2.0
            return temp_c
        else:
            print(f"Error reading register {register}: {result}")
            return None
    except Exception as e:
        print(f"Exception reading register {register}: {e}")
        return None


def read_status(client, register, status_map):
    """Read status value and map to description"""
    try:
        result = client.read_input_registers(register, count=1, slave=DEVICE_ID)
        if not result.isError():
            status_value = result.registers[0]
            status_desc = status_map.get(status_value, f"Unknown ({status_value})")
            return status_desc
        else:
            print(f"Error reading register {register}: {result}")
            return None
    except Exception as e:
        print(f"Exception reading register {register}: {e}")
        return None


def main():
    print(f"Connecting to Froeling T4e at {HOST}:{PORT}...")
    
    client = ModbusTcpClient(HOST, port=PORT)
    
    if not client.connect():
        print("Failed to connect to Froeling T4e")
        sys.exit(1)
    
    print("Connected successfully!\n")
    
    try:
        # Read buffer tank temperatures
        print("=== Buffer Tank Temperatures ===")
        temp_top = read_temperature(client, BUFFER_TEMP_TOP)
        temp_bottom = read_temperature(client, BUFFER_TEMP_BOTTOM)
        
        if temp_top is not None:
            print(f"Buffer Top:    {temp_top:.1f}°C")
        if temp_bottom is not None:
            print(f"Buffer Bottom: {temp_bottom:.1f}°C")
        if temp_top is not None and temp_bottom is not None:
            diff = temp_top - temp_bottom
            print(f"Difference:    {diff:.1f}°C")
        
        # Read operating status
        print("\n=== Operating Status ===")
        system_status = read_status(client, SYSTEM_STATUS, SYSTEM_STATUS_MAP)
        if system_status:
            print(f"System Status:  {system_status}")
        
        furnace_status = read_status(client, FURNACE_STATUS, FURNACE_STATUS_MAP)
        if furnace_status:
            print(f"Furnace Status: {furnace_status}")
        
    finally:
        client.close()
        print("\nConnection closed.")


if __name__ == "__main__":
    main()
