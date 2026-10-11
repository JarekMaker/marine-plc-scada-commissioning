# Modbus map — engine-room trainer

TCP port **5020**, unit id **1**. Addresses below are zero-based protocol addresses (the form pymodbus and a Modbus PDU use). The classic data-reference number is in parentheses.

Analog holding registers are scaled by 10. A level of `350` is 35.0%, a temperature of `415` is 41.5 °C, and a pressure of `45` is 4.5 bar.

The PLC scan is 250 ms. Alarm bits latch. Acknowledge marks them; reset drops a bit only after its process condition is gone. The simulator clears the acknowledge and reset coils itself after it acts on them.

## Coils (FC 01 read, FC 05/15 write)

- `0` (00001) — bilge pump 1 start command
- `1` (00002) — bilge pump 2 start command
- `2` (00003) — alarm acknowledge, all latched alarms
- `3` (00004) — alarm reset, latched alarms whose condition is clear
- `4` (00005) — bilge pump 1 auto. High ballast starts the pump; it stops again at 40%
- `16` (00017) — inject bilge pump 1 fail to start
- `17` (00018) — inject bilge pump 1 overload
- `18` (00019) — inject bilge pump 2 fault
- `19` (00020) — inject ballast tank 1 high level
- `20` (00021) — inject ballast tank 2 high level
- `21` (00022) — inject engine-room high temperature
- `22` (00023) — inject cooling-water low pressure
- `23` (00024) — inject fire zone 1
- `24` (00025) — inject fire zone 2
- `25` (00026) — inject fire zone 3
- `26` (00027) — inject main power loss
- `27` (00028) — freeze the heartbeat counter

Fail to start raises an alarm while a run request is present, either from the start coil or from auto demand. The pump does not report running feedback in that case. Main power loss also drops the run request. Heartbeat freeze keeps the TCP session up but stops register `5` from incrementing, so the SCADA watchdog can time out.

## Discrete inputs (FC 02)

- `0` (10001) — bilge pump 1 running
- `1` (10002) — bilge pump 1 fault (live condition)
- `2` (10003) — bilge pump 2 running
- `3` (10004) — bilge pump 2 fault
- `4` (10005) — fire zone 1 sensor
- `5` (10006) — fire zone 2 sensor
- `6` (10007) — fire zone 3 sensor
- `7` (10008) — main power healthy
- `8` (10009) — emergency power healthy
- `9` (10010) — bilge pump 1 auto demand

Fire sensors follow the injected condition. The alarm bit can stay latched after the sensor returns to normal. Emergency power stays healthy in this model when main power is lost.

## Holding registers (FC 03)

- `0` (40001) — ballast tank 1 level, 0.1%
- `1` (40002) — ballast tank 2 level, 0.1%
- `2` (40003) — engine-room temperature, 0.1 °C
- `3` (40004) — cooling-water pressure, 0.1 bar
- `4` (40005) — latched alarm bitfield
- `5` (40006) — heartbeat counter, increments every scan unless frozen
- `6` (40007) — PLC status, `1` while scanning
- `7` (40008) — acknowledged alarm bitfield
- `8` (40009) — ballast high threshold, `850` (85.0%)
- `9` (40010) — engine-room high temperature threshold, `700` (70.0 °C)
- `10` (40011) — cooling-water low pressure threshold, `20` (2.0 bar)

Normal published values: ballast 35.0% and 42.0%, temperature 41.5 °C, pressure 4.5 bar.

## Alarm bits in registers 4 and 7

- bit 0 — bilge pump 1 fail to start
- bit 1 — bilge pump 1 overload
- bit 2 — bilge pump 2 fault
- bit 3 — ballast tank 1 high level
- bit 4 — ballast tank 2 high level
- bit 5 — engine-room high temperature
- bit 6 — cooling-water low pressure
- bit 7 — fire zone 1
- bit 8 — fire zone 2
- bit 9 — fire zone 3
- bit 10 — main power loss

Communication loss is not a PLC bit. The SCADA sets it when register `5` does not change for 1.5 s, and it clears when the counter moves again. Downtime for that gap is what the availability figure uses.
