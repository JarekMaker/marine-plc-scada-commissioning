"""Simplified engine-room scan. One pass reads commands and latches alarms.

This is not a class-approved marine automation system. Alarm bits stay
latched after the field condition clears until a reset command arrives.
"""

from common.map import (
    ALARM_MASK,
    COIL_ACK,
    COIL_HEARTBEAT_FREEZE,
    COIL_INJECT_BALLAST1_HIGH,
    COIL_INJECT_BALLAST2_HIGH,
    COIL_INJECT_ER_HIGH_TEMP,
    COIL_INJECT_FIRE_1,
    COIL_INJECT_FIRE_2,
    COIL_INJECT_FIRE_3,
    COIL_INJECT_LOW_PRESSURE,
    COIL_INJECT_MAIN_POWER_LOSS,
    COIL_INJECT_PUMP1_FAIL,
    COIL_INJECT_PUMP1_OVERLOAD,
    COIL_INJECT_PUMP2_FAULT,
    COIL_PUMP1_START,
    COIL_PUMP2_START,
    COIL_RESET,
    FAULT_BALLAST,
    FAULT_PRESSURE,
    FAULT_TEMP,
    NORMAL_BALLAST_1,
    NORMAL_BALLAST_2,
    NORMAL_PRESSURE,
    NORMAL_TEMP,
    THRESH_BALLAST,
    THRESH_PRESSURE,
    THRESH_TEMP,
)


class Plant:
    def __init__(self) -> None:
        self.heartbeat = 0
        self.active = 0
        self.ack = 0
        self.ballast1 = NORMAL_BALLAST_1
        self.ballast2 = NORMAL_BALLAST_2
        self.temp = NORMAL_TEMP
        self.pressure = NORMAL_PRESSURE
        self.pump1_running = False
        self.pump2_running = False
        self.pump1_fault = False
        self.pump2_fault = False
        self.fire = [False, False, False]
        self.main_power_ok = True
        self.emergency_power_ok = True
        self.clear_ack = False
        self.clear_reset = False
        self.newly_latched = 0
        self.newly_cleared = 0

    def scan(self, coils: list[bool]) -> None:
        def commanded(address: int) -> bool:
            return bool(coils[address]) if address < len(coils) else False

        start1 = commanded(COIL_PUMP1_START)
        start2 = commanded(COIL_PUMP2_START)
        fail1 = commanded(COIL_INJECT_PUMP1_FAIL)
        overload1 = commanded(COIL_INJECT_PUMP1_OVERLOAD)
        fault2 = commanded(COIL_INJECT_PUMP2_FAULT)
        high1 = commanded(COIL_INJECT_BALLAST1_HIGH)
        high2 = commanded(COIL_INJECT_BALLAST2_HIGH)
        hot = commanded(COIL_INJECT_ER_HIGH_TEMP)
        low_pressure = commanded(COIL_INJECT_LOW_PRESSURE)
        fire = [
            commanded(COIL_INJECT_FIRE_1),
            commanded(COIL_INJECT_FIRE_2),
            commanded(COIL_INJECT_FIRE_3),
        ]
        power_loss = commanded(COIL_INJECT_MAIN_POWER_LOSS)
        freeze = commanded(COIL_HEARTBEAT_FREEZE)

        # Fail-to-start and overload both remove running feedback.
        self.pump1_running = start1 and not fail1 and not overload1
        self.pump1_fault = (start1 and fail1) or overload1
        self.pump2_running = start2 and not fault2
        self.pump2_fault = fault2

        self.ballast1 = FAULT_BALLAST if high1 else NORMAL_BALLAST_1
        self.ballast2 = FAULT_BALLAST if high2 else NORMAL_BALLAST_2
        self.temp = FAULT_TEMP if hot else NORMAL_TEMP
        self.pressure = FAULT_PRESSURE if low_pressure else NORMAL_PRESSURE
        self.fire = fire
        self.main_power_ok = not power_loss
        self.emergency_power_ok = True

        conditions = 0
        if start1 and fail1:
            conditions |= 1 << 0
        if overload1:
            conditions |= 1 << 1
        if fault2:
            conditions |= 1 << 2
        if self.ballast1 >= THRESH_BALLAST:
            conditions |= 1 << 3
        if self.ballast2 >= THRESH_BALLAST:
            conditions |= 1 << 4
        if self.temp >= THRESH_TEMP:
            conditions |= 1 << 5
        if self.pressure <= THRESH_PRESSURE:
            conditions |= 1 << 6
        for index, active in enumerate(fire):
            if active:
                conditions |= 1 << (7 + index)
        if not self.main_power_ok:
            conditions |= 1 << 10
        conditions &= ALARM_MASK

        previous = self.active
        # Latch: a bit stays set after the sensor returns to normal.
        self.active |= conditions
        self.newly_latched = self.active & ~previous

        if commanded(COIL_ACK):
            self.ack |= self.active
            self.clear_ack = True
        else:
            self.clear_ack = False

        if commanded(COIL_RESET):
            # Reset only drops alarms whose process condition is already gone.
            clearable = self.active & ~conditions
            self.active &= ~clearable
            self.clear_reset = True
        else:
            self.clear_reset = False

        self.ack &= self.active
        self.newly_cleared = previous & ~self.active

        if not freeze:
            self.heartbeat = (self.heartbeat + 1) & 0xFFFF

    def discrete_inputs(self) -> list[int]:
        return [
            int(self.pump1_running),
            int(self.pump1_fault),
            int(self.pump2_running),
            int(self.pump2_fault),
            int(self.fire[0]),
            int(self.fire[1]),
            int(self.fire[2]),
            int(self.main_power_ok),
            int(self.emergency_power_ok),
        ]

    def holding_registers(self) -> list[int]:
        return [
            self.ballast1,
            self.ballast2,
            self.temp,
            self.pressure,
            self.active,
            self.heartbeat,
            1,
            self.ack,
            THRESH_BALLAST,
            THRESH_TEMP,
            THRESH_PRESSURE,
        ]
