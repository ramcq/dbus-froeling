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


def read_temperature(client, register):
    """Read temperature from register (value is in °C * 2)"""
    try:
        result = client.read_input_registers(register, count=1, unit=DEVICE_ID)
        
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
        result = client.read_input_registers(register, count=1, unit=DEVICE_ID)
        
        if not result.isError():
            status_value = result.registers[0]
            status_desc = status_map.get(status_value, f"Unknown ({status_value})")
            return status_value, status_desc
        else:
            print(f"Error reading register {register}: {result}")
            return None, None
            
    except Exception as e:
        print(f"Exception reading register {register}: {e}")
        return None, None


def main():
    print(f"Connecting to Froeling T4e at {HOST}:{PORT}...")
    print(f"Using Device ID: {DEVICE_ID}\n")
    
    client = ModbusTcpClient(HOST, port=PORT)
    
    if not client.connect():
        print("Failed to connect to Froeling T4e")
        print("\nTroubleshooting:")
        print("1. Check if Froeling IP is correct")
        print("2. Check if port 502 is open (try: nc -zv 192.168.1.245 502)")
        print("3. Verify Modbus TCP is enabled on the Froeling")
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
        system_code, system_status = read_status(client, SYSTEM_STATUS, SYSTEM_STATUS_MAP)
        if system_status:
            print(f"System Status:  {system_status} (code: {system_code})")
        
        furnace_code, furnace_status = read_status(client, FURNACE_STATUS, FURNACE_STATUS_MAP)
        if furnace_status:
            print(f"Furnace Status: {furnace_status} (code: {furnace_code})")
            
            # Show operating state
            if furnace_code is not None:
                # Boiler is considered "operating" when actively heating or preparing to heat
                # Includes: heating, fire maintenance, preparation, ignition, and related states
                # Excludes: off, faults, errors, door open, cleaning, shutdown sequences
                OPERATING_STATES = {
                    2, 3, 4,      # Heating Up, Heating, Fire Maintenance
                    7, 8, 9,      # Preparation, Pre-heating, Ignition
                    17,           # Suction Heating
                    27, 34, 38,   # Pre-heating Ignition, Re-ignition, FB: Ignition
                    56,           # Pre-ventilation
                    60, 61,       # AB: Heating Up, AB: Heating
                    70, 71, 72, 73,  # Heating - Cleaning, LW Heating Up, LW Heating, LW Heat/Shutdown
                    80            # LW Ignition
                }
                operating = furnace_code in OPERATING_STATES
                print(f"Boiler Operating: {'YES' if operating else 'NO'}")
        
    finally:
        client.close()
        print("\nConnection closed.")


if __name__ == "__main__":
    main()
