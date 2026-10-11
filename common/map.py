"""Modbus map and process constants for the training simulator.

Protocol addresses are zero-based, which is what Modbus TCP PDUs and
pymodbus use. Classic coil/register numbers are noted in plc/modbus_map.md.
"""

PLC_PORT = 5020
SCAN_SECONDS = 0.25
# SCADA declares the PLC offline when the heartbeat register stops changing.
HEARTBEAT_STALE_SECONDS = 1.5

# Coils, function 01/05/15.
COIL_PUMP1_START = 0
COIL_PUMP2_START = 1
COIL_ACK = 2
COIL_RESET = 3
COIL_PUMP1_AUTO = 4
COIL_INJECT_PUMP1_FAIL = 16
COIL_INJECT_PUMP1_OVERLOAD = 17
COIL_INJECT_PUMP2_FAULT = 18
COIL_INJECT_BALLAST1_HIGH = 19
COIL_INJECT_BALLAST2_HIGH = 20
COIL_INJECT_ER_HIGH_TEMP = 21
COIL_INJECT_LOW_PRESSURE = 22
COIL_INJECT_FIRE_1 = 23
COIL_INJECT_FIRE_2 = 24
COIL_INJECT_FIRE_3 = 25
COIL_INJECT_MAIN_POWER_LOSS = 26
COIL_HEARTBEAT_FREEZE = 27

FAULT_COIL_START = 16
FAULT_COIL_COUNT = 12

# Discrete inputs, function 02.
DI_PUMP1_RUNNING = 0
DI_PUMP1_FAULT = 1
DI_PUMP2_RUNNING = 2
DI_PUMP2_FAULT = 3
DI_FIRE_1 = 4
DI_FIRE_2 = 5
DI_FIRE_3 = 6
DI_MAIN_POWER_OK = 7
DI_EMERGENCY_POWER_OK = 8
DI_PUMP1_AUTO_DEMAND = 9
DI_COUNT = 10

# Holding registers, function 03. Analog values are in tenths.
HR_BALLAST1 = 0
HR_BALLAST2 = 1
HR_ER_TEMP = 2
HR_COOLING_PRESSURE = 3
HR_ALARM_WORD = 4
HR_HEARTBEAT = 5
HR_PLC_STATUS = 6
HR_ACK_WORD = 7
HR_THRESH_BALLAST = 8
HR_THRESH_TEMP = 9
HR_THRESH_PRESSURE = 10
HR_COUNT = 11

# Tenths of a percent, degree C, or bar.
THRESH_BALLAST = 850
THRESH_TEMP = 700
THRESH_PRESSURE = 20

NORMAL_BALLAST_1 = 350
NORMAL_BALLAST_2 = 420
NORMAL_TEMP = 415
NORMAL_PRESSURE = 45

FAULT_BALLAST = 920
FAULT_TEMP = 820
FAULT_PRESSURE = 12

# Tenths of a percent, applied once per 250 ms scan.
BALLAST_STOP = 400
INGRESS_PER_SCAN = 6
PUMPDOWN_PER_SCAN = 16
STANDBY_PER_SCAN = 24

ALARMS = [
    {"bit": 0, "id": "pump1_fail_to_start", "name": "Bilge pump 1 fail to start", "priority": "high"},
    {"bit": 1, "id": "pump1_overload", "name": "Bilge pump 1 overload", "priority": "high"},
    {"bit": 2, "id": "pump2_fault", "name": "Bilge pump 2 fault", "priority": "high"},
    {"bit": 3, "id": "ballast1_high", "name": "Ballast tank 1 high level", "priority": "medium"},
    {"bit": 4, "id": "ballast2_high", "name": "Ballast tank 2 high level", "priority": "medium"},
    {"bit": 5, "id": "er_high_temp", "name": "Engine room high temperature", "priority": "high"},
    {"bit": 6, "id": "cooling_low_pressure", "name": "Cooling water low pressure", "priority": "high"},
    {"bit": 7, "id": "fire_zone_1", "name": "Fire zone 1", "priority": "critical"},
    {"bit": 8, "id": "fire_zone_2", "name": "Fire zone 2", "priority": "critical"},
    {"bit": 9, "id": "fire_zone_3", "name": "Fire zone 3", "priority": "critical"},
    {"bit": 10, "id": "main_power_loss", "name": "Main power loss", "priority": "critical"},
]

FAULTS = [
    {"id": "pump1_fail_to_start", "coil": COIL_INJECT_PUMP1_FAIL, "label": "Bilge pump 1 fail to start"},
    {"id": "pump1_overload", "coil": COIL_INJECT_PUMP1_OVERLOAD, "label": "Bilge pump 1 overload"},
    {"id": "pump2_fault", "coil": COIL_INJECT_PUMP2_FAULT, "label": "Bilge pump 2 fault"},
    {"id": "ballast1_high", "coil": COIL_INJECT_BALLAST1_HIGH, "label": "Ballast tank 1 high level"},
    {"id": "ballast2_high", "coil": COIL_INJECT_BALLAST2_HIGH, "label": "Ballast tank 2 high level"},
    {"id": "er_high_temp", "coil": COIL_INJECT_ER_HIGH_TEMP, "label": "Engine room high temperature"},
    {"id": "cooling_low_pressure", "coil": COIL_INJECT_LOW_PRESSURE, "label": "Cooling water low pressure"},
    {"id": "fire_zone_1", "coil": COIL_INJECT_FIRE_1, "label": "Fire zone 1"},
    {"id": "fire_zone_2", "coil": COIL_INJECT_FIRE_2, "label": "Fire zone 2"},
    {"id": "fire_zone_3", "coil": COIL_INJECT_FIRE_3, "label": "Fire zone 3"},
    {"id": "main_power_loss", "coil": COIL_INJECT_MAIN_POWER_LOSS, "label": "Main power loss"},
    {"id": "heartbeat_freeze", "coil": COIL_HEARTBEAT_FREEZE, "label": "Freeze PLC heartbeat"},
]

FAULT_BY_ID = {item["id"]: item for item in FAULTS}
ALARM_BY_ID = {item["id"]: item for item in ALARMS}
ALARM_MASK = (1 << len(ALARMS)) - 1


def tenths(raw: int) -> float:
    return raw / 10.0
