"""Modbus client, watchdog, and commissioning steps.

Every process value is read back from the PLC. Faults are coils on that
map, not local variables.
"""

import asyncio
import logging
import os
import time
from typing import Any, Callable

from pymodbus.client import AsyncModbusTcpClient

from common.map import (
    ALARMS,
    COIL_ACK,
    COIL_HEARTBEAT_FREEZE,
    COIL_INJECT_FIRE_1,
    COIL_INJECT_MAIN_POWER_LOSS,
    COIL_INJECT_PUMP1_FAIL,
    COIL_PUMP1_START,
    COIL_PUMP2_START,
    COIL_RESET,
    DI_COUNT,
    FAULT_BY_ID,
    FAULT_COIL_COUNT,
    FAULT_COIL_START,
    FAULTS,
    HEARTBEAT_STALE_SECONDS,
    HR_COUNT,
    PLC_PORT,
    THRESH_BALLAST,
    THRESH_PRESSURE,
    THRESH_TEMP,
    tenths,
)

log = logging.getLogger("trainer.scada")

STEPS = [
    {
        "id": "heartbeat_online",
        "title": "PLC heartbeat online",
        "expected": "Holding register 40006 increments while the link is up.",
    },
    {
        "id": "pump1_start_feedback",
        "title": "Pump 1 start and running feedback",
        "expected": "Start command sets discrete input 10001 within one PLC scan.",
    },
    {
        "id": "pump1_fail_to_start",
        "title": "Pump 1 fail-to-start alarm and acknowledge",
        "expected": "No running feedback, alarm bit 0 latches, then acknowledge sets bit 0 in register 40008.",
    },
    {
        "id": "ballast1_high_level",
        "title": "Ballast tank 1 high level",
        "expected": "Level reaches at least 85% and alarm bit 3 latches.",
    },
    {
        "id": "fire_zone_alarm_reset",
        "title": "Fire zone alarm and reset",
        "expected": "Zone 1 sensor alarms, the alarm stays latched after the sensor clears, then reset drops it.",
    },
    {
        "id": "main_power_loss",
        "title": "Main power loss",
        "expected": "Main power discrete input drops, emergency power stays healthy, alarm bit 10 latches.",
    },
    {
        "id": "comms_loss_recovery",
        "title": "Communication loss and recovery",
        "expected": "Heartbeat freeze trips the SCADA watchdog, then clearing it restores the link and adds downtime.",
    },
]
STEP_BY_ID = {item["id"]: item for item in STEPS}


class StepError(Exception):
    def __init__(self, notes: str, response_time_ms: int | None = None) -> None:
        super().__init__(notes)
        self.notes = notes
        self.response_time_ms = response_time_ms


class BusyError(Exception):
    pass


class Supervisor:
    def __init__(self) -> None:
        self.host = os.environ.get("PLC_HOST", "127.0.0.1")
        self.port = int(os.environ.get("PLC_PORT", str(PLC_PORT)))
        self.lock = asyncio.Lock()
        self.client: AsyncModbusTcpClient | None = None
        self.task: asyncio.Task | None = None
        self.step_running = False
        self._logged_down = False
        self.connected = False
        self.comms_ok = False
        self.seen = False
        self.last_hb: int | None = None
        self.last_change = 0.0
        self.monitor_from: float | None = None
        self.down_since: float | None = None
        self.downtime_total = 0.0
        self.alarm_word = 0
        self.ack_word = 0
        self.heartbeat = 0
        self.registers = [0] * HR_COUNT
        self.discrete = [False] * DI_COUNT
        self.coils = [False] * 32
        self.view: dict[str, Any] = {}
        self.reports = {
            item["id"]: {
                **item,
                "result": "not_run",
                "response_time_ms": None,
                "notes": "",
            }
            for item in STEPS
        }
        self._view()

    async def start(self) -> None:
        self.task = asyncio.create_task(self._poll())
        log.info("Watching PLC at %s:%s", self.host, self.port)

    async def stop(self) -> None:
        if self.task:
            self.task.cancel()
        if self.client:
            self.client.close()

    async def _poll(self) -> None:
        while True:
            try:
                await self._read_once()
            except Exception:
                log.exception("Poll failed")
                self._mark_down(time.monotonic())
                self._view()
            await asyncio.sleep(0.2)

    async def snapshot(self) -> dict[str, Any]:
        return self.view

    def steps(self) -> list[dict[str, Any]]:
        return [self.reports[item["id"]] for item in STEPS]

    async def acknowledge(self) -> None:
        self._ensure_idle()
        await self._write_coil(COIL_ACK, True)

    async def reset(self) -> None:
        self._ensure_idle()
        await self._write_coil(COIL_RESET, True)

    async def set_commands(self, pump1_start: bool | None, pump2_start: bool | None) -> None:
        self._ensure_idle()
        async with self.lock:
            await self._connect_unlocked()
            current = await self.client.read_coils(0, 2, slave=1)
            if current.isError():
                raise StepError("Could not read pump command coils.")
            values = [bool(current.bits[0]), bool(current.bits[1])]
            if pump1_start is not None:
                values[0] = pump1_start
            if pump2_start is not None:
                values[1] = pump2_start
            wrote = await self.client.write_coils(0, values, slave=1)
            if wrote.isError():
                raise StepError("Could not write pump command coils.")

    async def inject(self, fault_id: str) -> None:
        self._ensure_idle()
        await self._inject_unlocked_public(fault_id)

    async def run_step(self, step_id: str) -> dict[str, Any]:
        spec = STEP_BY_ID.get(step_id)
        if spec is None:
            raise KeyError(step_id)
        if self.step_running:
            raise BusyError()
        self.step_running = True
        try:
            result, response_ms, notes = await self._dispatch(step_id)
            report = {
                **spec,
                "result": result,
                "response_time_ms": response_ms,
                "notes": notes,
            }
        except StepError as exc:
            report = {
                **spec,
                "result": "fail",
                "response_time_ms": exc.response_time_ms,
                "notes": exc.notes,
            }
        except Exception as exc:
            log.exception("Step %s failed", step_id)
            report = {
                **spec,
                "result": "fail",
                "response_time_ms": None,
                "notes": str(exc),
            }
        finally:
            self.step_running = False
        self.reports[step_id] = report
        log.info("Step %s -> %s (%s)", step_id, report["result"], report["notes"])
        return report

    def tag_list(self) -> list[dict[str, Any]]:
        view = self.view
        pumps = {item["id"]: item for item in view.get("pumps", [])}
        tanks = {item["id"]: item for item in view.get("tanks", [])}
        fire = view.get("fire_zones", [False, False, False])
        rows = [
            ("ballast1_level", tanks.get("ballast1", {}).get("level_percent"), "%", "40001"),
            ("ballast2_level", tanks.get("ballast2", {}).get("level_percent"), "%", "40002"),
            ("er_temperature", view.get("er_temp_c"), "°C", "40003"),
            ("cooling_pressure", view.get("cooling_pressure_bar"), "bar", "40004"),
            ("alarm_word", view.get("alarm_word"), "", "40005"),
            ("heartbeat", view.get("heartbeat"), "", "40006"),
            ("ack_word", view.get("ack_word"), "", "40008"),
            ("pump1_running", int(pumps.get("pump1", {}).get("running", False)), "", "10001"),
            ("pump1_fault", int(pumps.get("pump1", {}).get("fault", False)), "", "10002"),
            ("pump2_running", int(pumps.get("pump2", {}).get("running", False)), "", "10003"),
            ("pump2_fault", int(pumps.get("pump2", {}).get("fault", False)), "", "10004"),
            ("fire_zone_1", int(fire[0]) if len(fire) > 0 else 0, "", "10005"),
            ("fire_zone_2", int(fire[1]) if len(fire) > 1 else 0, "", "10006"),
            ("fire_zone_3", int(fire[2]) if len(fire) > 2 else 0, "", "10007"),
            ("main_power_ok", int(view.get("main_power_ok", False)), "", "10008"),
            ("emergency_power_ok", int(view.get("emergency_power_ok", False)), "", "10009"),
            ("pump1_start_cmd", int(pumps.get("pump1", {}).get("start_command", False)), "", "00001"),
            ("pump2_start_cmd", int(pumps.get("pump2", {}).get("start_command", False)), "", "00002"),
        ]
        return [
            {"name": name, "value": value, "unit": unit, "register": register}
            for name, value, unit, register in rows
        ]

    def _ensure_idle(self) -> None:
        if self.step_running:
            raise BusyError()

    async def _dispatch(self, step_id: str) -> tuple[str, int | None, str]:
        await self._baseline()
        if step_id == "heartbeat_online":
            return await self._step_heartbeat()
        if step_id == "pump1_start_feedback":
            return await self._step_pump_start()
        if step_id == "pump1_fail_to_start":
            return await self._step_fail_to_start()
        if step_id == "ballast1_high_level":
            return await self._step_ballast()
        if step_id == "fire_zone_alarm_reset":
            return await self._step_fire()
        if step_id == "main_power_loss":
            return await self._step_power()
        if step_id == "comms_loss_recovery":
            return await self._step_comms()
        raise KeyError(step_id)

    async def _baseline(self) -> None:
        await self._write_coil(COIL_PUMP1_START, False)
        await self._write_coil(COIL_PUMP2_START, False)
        await self._write_faults("none")
        healthy = await self._wait(self._process_healthy, 3.0)
        if healthy is None:
            raise StepError("Process did not return to normal setpoints before the test.")
        await self._write_coil(COIL_RESET, True)
        settled = await self._wait(
            lambda snap: snap["alarm_word"] == 0 and not snap["coils"][COIL_RESET] and snap["comms_ok"],
            3.0,
        )
        if settled is None:
            raise StepError("Reset did not clear the latched alarm word.")

    async def _step_heartbeat(self) -> tuple[str, int, str]:
        start = await self._require_read()
        start_hb = start["heartbeat"]
        t0 = time.monotonic()
        changed = await self._wait(lambda snap: snap["heartbeat"] != start_hb and snap["comms_ok"], 3.0)
        elapsed = int((time.monotonic() - t0) * 1000)
        if changed is None:
            raise StepError("Heartbeat register did not increment.", elapsed)
        return (
            "pass",
            elapsed,
            f"Heartbeat {start_hb} -> {changed['heartbeat']} in {elapsed} ms.",
        )

    async def _step_pump_start(self) -> tuple[str, int, str]:
        t0 = time.monotonic()
        await self._write_coil(COIL_PUMP1_START, True)
        snap = await self._wait(lambda item: item["pumps"][0]["running"] and not (item["alarm_word"] & 0b11), 3.0)
        elapsed = int((time.monotonic() - t0) * 1000)
        if snap is None:
            raise StepError("Pump 1 running feedback did not arrive.", elapsed)
        return ("pass", elapsed, f"Running feedback on discrete input 10001 in {elapsed} ms.")

    async def _step_fail_to_start(self) -> tuple[str, int, str]:
        t0 = time.monotonic()
        await self._write_coil(COIL_INJECT_PUMP1_FAIL, True)
        await self._write_coil(COIL_PUMP1_START, True)

        def appeared(snap: dict[str, Any]) -> bool:
            if snap["pumps"][0]["running"]:
                raise StepError("Pump 1 reported running during a fail-to-start test.")
            return bool(snap["alarm_word"] & 1)

        snap = await self._wait(appeared, 3.0)
        elapsed = int((time.monotonic() - t0) * 1000)
        if snap is None:
            raise StepError("Fail-to-start alarm bit did not latch.", elapsed)
        await self._write_coil(COIL_ACK, True)
        acked = await self._wait(lambda item: bool(item["ack_word"] & 1) and bool(item["alarm_word"] & 1), 3.0)
        if acked is None:
            raise StepError("Alarm latched but acknowledge bit was not set.", elapsed)
        return (
            "pass",
            elapsed,
            f"Alarm bit 0 latched in {elapsed} ms and was acknowledged. Pump stayed stopped.",
        )

    async def _step_ballast(self) -> tuple[str, int, str]:
        t0 = time.monotonic()
        await self._write_faults("ballast1_high")

        def high(snap: dict[str, Any]) -> bool:
            level = snap["tanks"][0]["level_percent"]
            return level >= 85.0 and bool(snap["alarm_word"] & (1 << 3))

        snap = await self._wait(high, 3.0)
        elapsed = int((time.monotonic() - t0) * 1000)
        if snap is None:
            raise StepError("Ballast tank 1 did not reach the high-level alarm.", elapsed)
        level = snap["tanks"][0]["level_percent"]
        return ("pass", elapsed, f"Level {level:.1f}% and alarm bit 3 latched in {elapsed} ms.")

    async def _step_fire(self) -> tuple[str, int, str]:
        t0 = time.monotonic()
        await self._write_coil(COIL_INJECT_FIRE_1, True)
        detected = await self._wait(
            lambda snap: bool(snap["fire_zones"][0]) and bool(snap["alarm_word"] & (1 << 7)),
            3.0,
        )
        elapsed = int((time.monotonic() - t0) * 1000)
        if detected is None:
            raise StepError("Fire zone 1 alarm did not latch.", elapsed)
        await self._write_coil(COIL_INJECT_FIRE_1, False)
        latched = await self._wait(
            lambda snap: (not snap["fire_zones"][0]) and bool(snap["alarm_word"] & (1 << 7)),
            3.0,
        )
        if latched is None:
            raise StepError("Fire alarm did not stay latched after the sensor cleared.", elapsed)
        await self._write_coil(COIL_RESET, True)
        cleared = await self._wait(lambda snap: snap["alarm_word"] & (1 << 7) == 0, 3.0)
        if cleared is None:
            raise StepError("Reset did not drop the fire alarm after the sensor was normal.", elapsed)
        return (
            "pass",
            elapsed,
            f"Sensor alarm in {elapsed} ms, stayed latched after the sensor cleared, then reset.",
        )

    async def _step_power(self) -> tuple[str, int, str]:
        t0 = time.monotonic()
        await self._write_coil(COIL_INJECT_MAIN_POWER_LOSS, True)

        def lost(snap: dict[str, Any]) -> bool:
            return (
                (not snap["main_power_ok"])
                and snap["emergency_power_ok"]
                and bool(snap["alarm_word"] & (1 << 10))
            )

        snap = await self._wait(lost, 3.0)
        elapsed = int((time.monotonic() - t0) * 1000)
        if snap is None:
            raise StepError("Main power loss did not match the expected inputs and alarm bit.", elapsed)
        return (
            "pass",
            elapsed,
            f"Main power lost in {elapsed} ms. Emergency power stayed available. Alarm bit 10 latched.",
        )

    async def _step_comms(self) -> tuple[str, int, str]:
        t0 = time.monotonic()
        await self._write_coil(COIL_HEARTBEAT_FREEZE, True)
        lost = await self._wait(lambda snap: snap["connected"] and not snap["comms_ok"], 4.0)
        loss_ms = int((time.monotonic() - t0) * 1000)
        if lost is None:
            raise StepError("Watchdog did not declare heartbeat loss.", loss_ms)
        t1 = time.monotonic()
        await self._write_coil(COIL_HEARTBEAT_FREEZE, False)
        back = await self._wait(lambda snap: snap["comms_ok"], 3.0)
        recovery_ms = int((time.monotonic() - t1) * 1000)
        if back is None:
            raise StepError("Heartbeat did not recover after the freeze was cleared.", loss_ms)
        downtime = back["downtime_seconds"]
        return (
            "pass",
            loss_ms,
            f"Loss detected in {loss_ms} ms. Recovery in {recovery_ms} ms. Downtime {downtime:.1f} s.",
        )

    async def _inject_unlocked_public(self, fault_id: str) -> None:
        await self._write_faults(fault_id)
        if fault_id == "pump1_fail_to_start":
            await self._write_coil(COIL_PUMP1_START, True)

    async def _write_faults(self, fault_id: str) -> None:
        values = [False] * FAULT_COIL_COUNT
        if fault_id != "none":
            spec = FAULT_BY_ID.get(fault_id)
            if spec is None:
                raise StepError(f"Unknown fault '{fault_id}'.")
            values[spec["coil"] - FAULT_COIL_START] = True
        async with self.lock:
            await self._connect_unlocked()
            wrote = await self.client.write_coils(FAULT_COIL_START, values, slave=1)
            if wrote.isError():
                raise StepError("Could not write fault-injection coils.")

    async def _write_coil(self, address: int, value: bool) -> None:
        async with self.lock:
            await self._connect_unlocked()
            wrote = await self.client.write_coil(address, value, slave=1)
            if wrote.isError():
                raise StepError(f"Could not write coil {address}.")

    async def _require_read(self) -> dict[str, Any]:
        snap = await self._read_once()
        if not snap["connected"]:
            raise StepError("No Modbus link to the PLC.")
        return snap

    async def _wait(self, predicate: Callable[[dict[str, Any]], bool], timeout: float) -> dict[str, Any] | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            snap = await self._read_once()
            if snap["connected"] and predicate(snap):
                return snap
            await asyncio.sleep(0.05)
        return None

    async def _read_once(self) -> dict[str, Any]:
        async with self.lock:
            try:
                await self._connect_unlocked()
                holding = await self.client.read_holding_registers(0, HR_COUNT, slave=1)
                discrete = await self.client.read_discrete_inputs(0, DI_COUNT, slave=1)
                coils = await self.client.read_coils(0, 32, slave=1)
            except Exception as exc:
                self._log_down(exc)
                self._mark_down(time.monotonic())
                return self._view()
            if holding.isError() or discrete.isError() or coils.isError():
                self._log_down("Modbus exception on read")
                self._mark_down(time.monotonic())
                return self._view()
            self.connected = True
            self._logged_down = False
            self.registers = list(holding.registers)
            self.discrete = [bool(bit) for bit in discrete.bits[:DI_COUNT]]
            self.coils = [bool(bit) for bit in coils.bits[:32]]
            self._note_heartbeat(self.registers[5], time.monotonic())
            return self._view()

    async def _connect_unlocked(self) -> None:
        if self.client and self.client.connected:
            return
        if self.client:
            self.client.close()
        self.client = AsyncModbusTcpClient(self.host, port=self.port)
        connected = await self.client.connect()
        if not connected:
            raise ConnectionError(f"PLC {self.host}:{self.port} refused the connection")

    def _note_heartbeat(self, heartbeat: int, now: float) -> None:
        if not self.seen:
            self.seen = True
            self.last_hb = heartbeat
            self.last_change = now
            self.monitor_from = now
            self.comms_ok = True
            self.heartbeat = heartbeat
            return
        self.heartbeat = heartbeat
        if heartbeat != self.last_hb:
            self.last_hb = heartbeat
            self.last_change = now
            if not self.comms_ok and self.down_since is not None:
                self.downtime_total += now - self.down_since
                self.down_since = None
            self.comms_ok = True
            return
        if (now - self.last_change) >= HEARTBEAT_STALE_SECONDS and self.comms_ok:
            self.comms_ok = False
            # Count from the last live heartbeat, not from the moment the watchdog fired.
            self.down_since = self.last_change

    def _log_down(self, exc: object) -> None:
        if not self._logged_down:
            log.warning("Modbus read failed: %s", exc)
            self._logged_down = True

    def _mark_down(self, now: float) -> None:
        self.connected = False
        self.comms_ok = False
        if self.seen and self.down_since is None:
            self.down_since = now

    def _process_healthy(self, snap: dict[str, Any]) -> bool:
        if snap["active_faults"] or not snap["comms_ok"] or not snap["main_power_ok"]:
            return False
        if any(snap["fire_zones"]):
            return False
        if snap["pumps"][0]["running"] or snap["pumps"][1]["running"]:
            return False
        if snap["tanks"][0]["level_percent"] >= 85 or snap["tanks"][1]["level_percent"] >= 85:
            return False
        if snap["er_temp_c"] >= 70 or snap["cooling_pressure_bar"] <= 2:
            return False
        return True

    def _view(self) -> dict[str, Any]:
        now = time.monotonic()
        downtime = self.downtime_total
        if self.down_since is not None:
            downtime += now - self.down_since
        elapsed = (now - self.monitor_from) if self.monitor_from else 0.0
        availability = None
        if self.monitor_from and elapsed > 0:
            availability = round(max(0.0, (elapsed - downtime) / elapsed * 100.0), 1)

        regs = self.registers
        coils = self.coils
        discrete = self.discrete + [False] * (DI_COUNT - len(self.discrete))
        alarm_word = regs[4] if len(regs) > 4 else self.alarm_word
        ack_word = regs[7] if len(regs) > 7 else self.ack_word
        self.alarm_word = alarm_word
        self.ack_word = ack_word

        alarms = []
        for spec in ALARMS:
            mask = 1 << spec["bit"]
            if alarm_word & mask:
                alarms.append(
                    {
                        "id": spec["id"],
                        "name": spec["name"],
                        "priority": spec["priority"],
                        "active": True,
                        "acknowledged": bool(ack_word & mask),
                    }
                )
        if self.seen and not self.comms_ok:
            alarms.insert(
                0,
                {
                    "id": "comms_loss",
                    "name": "SCADA watchdog — PLC heartbeat lost",
                    "priority": "critical",
                    "active": True,
                    "acknowledged": False,
                },
            )

        active_faults = [
            {"id": item["id"], "label": item["label"]}
            for item in FAULTS
            if item["coil"] < len(coils) and coils[item["coil"]]
        ]

        self.view = {
            "connected": self.connected,
            "comms_ok": self.comms_ok and self.connected,
            "availability_percent": availability,
            "downtime_seconds": round(downtime, 1),
            "heartbeat": regs[5] if len(regs) > 5 else self.heartbeat,
            "alarm_word": alarm_word,
            "ack_word": ack_word,
            "coils": coils,
            "pumps": [
                {
                    "id": "pump1",
                    "name": "Bilge pump 1",
                    "running": discrete[0],
                    "fault": discrete[1],
                    "start_command": coils[0] if coils else False,
                },
                {
                    "id": "pump2",
                    "name": "Bilge pump 2",
                    "running": discrete[2],
                    "fault": discrete[3],
                    "start_command": coils[1] if len(coils) > 1 else False,
                },
            ],
            "tanks": [
                {"id": "ballast1", "name": "Ballast tank 1", "level_percent": tenths(regs[0]) if regs else 0},
                {"id": "ballast2", "name": "Ballast tank 2", "level_percent": tenths(regs[1]) if len(regs) > 1 else 0},
            ],
            "er_temp_c": tenths(regs[2]) if len(regs) > 2 else 0,
            "cooling_pressure_bar": tenths(regs[3]) if len(regs) > 3 else 0,
            "fire_zones": [discrete[4], discrete[5], discrete[6]],
            "main_power_ok": discrete[7],
            "emergency_power_ok": discrete[8],
            "active_faults": active_faults,
            "alarms": alarms,
            "thresholds": {
                "ballast_high_percent": tenths(THRESH_BALLAST),
                "er_temp_high_c": tenths(THRESH_TEMP),
                "cooling_low_bar": tenths(THRESH_PRESSURE),
            },
            "step_running": self.step_running,
        }
        return self.view
