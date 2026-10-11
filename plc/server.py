"""Modbus TCP slave for the engine-room trainer.

The SCADA never imports this process. It only reads and writes the map
published here. Default port is 5020 so the simulator does not need the
privileged Modbus port 502.
"""

import asyncio
import logging
import os

from pymodbus.datastore import ModbusSequentialDataBlock, ModbusServerContext, ModbusSlaveContext
from pymodbus.server import StartAsyncTcpServer

from common.map import (
    ALARMS,
    COIL_ACK,
    COIL_RESET,
    DI_COUNT,
    HR_COUNT,
    PLC_PORT,
    SCAN_SECONDS,
)
from plc.process import Plant

log = logging.getLogger("trainer.plc")


def _alarm_names(mask: int) -> str:
    names = [item["name"] for item in ALARMS if mask & (1 << item["bit"])]
    return ", ".join(names) if names else "none"


def build_context() -> ModbusServerContext:
    # zero_mode keeps protocol address 0 on the first value. The default
    # pymodbus slave context otherwise shifts every address by one.
    store = ModbusSlaveContext(
        di=ModbusSequentialDataBlock(0, [0] * DI_COUNT),
        co=ModbusSequentialDataBlock(0, [0] * 32),
        hr=ModbusSequentialDataBlock(0, [0] * HR_COUNT),
        ir=ModbusSequentialDataBlock(0, [0] * 8),
        zero_mode=True,
    )
    return ModbusServerContext(slaves=store, single=True)


def publish(context: ModbusServerContext, plant: Plant) -> None:
    slave = context[0]
    slave.setValues(2, 0, plant.discrete_inputs())
    slave.setValues(3, 0, plant.holding_registers())
    if plant.clear_ack:
        slave.setValues(1, COIL_ACK, [0])
    if plant.clear_reset:
        slave.setValues(1, COIL_RESET, [0])


def read_coils(context: ModbusServerContext, count: int = 32) -> list[bool]:
    raw = context[0].getValues(1, 0, count)
    return [bool(value) for value in raw]


async def scan_loop(context: ModbusServerContext) -> None:
    plant = Plant()
    publish(context, plant)
    log.info("Initial image published. Heartbeat=%s", plant.heartbeat)
    while True:
        plant.scan(read_coils(context))
        publish(context, plant)
        if plant.newly_latched:
            log.info("Alarm latched: %s", _alarm_names(plant.newly_latched))
        if plant.newly_cleared:
            log.info("Alarm reset: %s", _alarm_names(plant.newly_cleared))
        await asyncio.sleep(SCAN_SECONDS)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    host = os.environ.get("PLC_BIND", "0.0.0.0")
    port = int(os.environ.get("PLC_PORT", str(PLC_PORT)))
    context = build_context()
    scanner = asyncio.create_task(scan_loop(context))
    log.info("Engine-room PLC simulator listening on %s:%s", host, port)
    try:
        await StartAsyncTcpServer(context=context, address=(host, port))
    finally:
        scanner.cancel()


if __name__ == "__main__":
    asyncio.run(main())
