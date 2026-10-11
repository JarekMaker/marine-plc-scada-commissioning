# Functional commissioning checklist

Run these from the SCADA page (**Commissioning checklist**) or with `POST /api/commissioning/steps/{id}/run`. Each step first turns pump 1 auto off, clears injected faults, stops both pumps, and resets latched alarms. It then creates one condition and waits for the expected Modbus result. Response time is the time from the command until that result appears. **Export report** downloads the sheet.

Pass and fail stay on the step after the run. A failed step does not change the wording of the others.

## 1. PLC heartbeat online

- Id: `heartbeat_online`
- Action: read holding register 40006, wait until the counter changes.
- Pass: the counter increments and the link stays online.
- Evidence: `40006 heartbeat {before} -> {after}`.

## 2. Pump 1 start and running feedback

- Id: `pump1_start_feedback`
- Action: set coil 00001 (pump 1 start).
- Pass: discrete input 10001 (running) becomes 1 within 3 s, and pump-fault alarm bits stay clear.
- Evidence: running feedback time.

## 3. Pump 1 fail-to-start alarm and acknowledge

- Id: `pump1_fail_to_start`
- Action: set coil 00017 (fail to start), then set coil 00001 (start). Pulse coil 00003 (acknowledge).
- Pass: discrete input 10001 stays 0, alarm bit 0 latches in register 40005, then bit 0 is set in register 40008.
- Evidence: time from the fault coil until the alarm bit, and the acknowledge bit.

## 4. Ballast tank 1 high level

- Id: `ballast1_high_level`
- Action: set coil 00020.
- Pass: register 40001 is at least 85.0% and alarm bit 3 is latched.
- Evidence: level and response time. The high mark on the tank is 85%.

## 5. High level auto-starts pump 1

- Id: `ballast1_auto_start`
- Action: set coil 00005 (pump 1 auto), then set coil 00020.
- Pass: discrete input 10010 (auto demand) and 10001 (running) are both 1, level stays at least 85%, and alarm bit 3 is latched.
- Evidence: time from the high-level injection until the pump reports running. The injected level is held, so the pump does not pump the tank back down until the fault coil is cleared.

## 6. Fire zone alarm and reset

- Id: `fire_zone_alarm_reset`
- Action: set coil 00024 (fire zone 1). After the alarm latches, clear that coil, then pulse coil 00004 (reset).
- Pass: discrete input 10005 follows the sensor. Alarm bit 7 stays latched after the sensor returns to normal, and reset drops it only then.
- Evidence: response time plus the latch-and-reset sequence. This is the difference between a live sensor and a latched alarm.

## 7. Main power loss

- Id: `main_power_loss`
- Action: set coil 00027.
- Pass: discrete input 10008 is 0, discrete input 10009 (emergency power) stays 1, and alarm bit 10 is latched.
- Evidence: both power inputs and the alarm bit.

## 8. Communication loss and recovery

- Id: `comms_loss_recovery`
- Action: set coil 00028 to freeze register 40006. The TCP session stays up. Clear the coil after the watchdog trips.
- Pass: the SCADA declares the heartbeat lost (no change for 1.5 s), then declares it healthy again after the counter moves. The lost interval is added to downtime and availability falls by that amount.
- Evidence: detection time, recovery time, and downtime seconds.

Manual fault injection uses the same coils. Choose a fault under **Alarms** and press Apply. **Clear injected faults** writes those coils back to 0. Acknowledge and reset are the same coils the checklist pulses.
