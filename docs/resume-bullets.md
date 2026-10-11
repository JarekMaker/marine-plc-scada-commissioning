# Resume block

Paste this under Personal Projects. It describes this repository only.

**Marine Auxiliary Commissioning Trainer (PLC/SCADA)**
Personal Project | 2026

- Built a Modbus TCP plant simulator and a single-page SCADA view of a simplified vessel engine room: bilge pumps, ballast levels, fire zones, power status, and a live trend.
- Implemented alarm detection, acknowledgement, and reset, plus an automatic bilge start when ballast reaches 85%.
- Wrote a functional commissioning checklist with a downloadable pass/fail report: inject a known fault, confirm the expected alarm, and record the response time.
- Ran the PLC simulator and REST API as Docker services on a documented Modbus register map and fixed network ports.

## How to say it in an interview

This is a personal trainer built to practise the commissioning loop for PLC/SCADA: a Modbus register map, latched alarms, and a checklist that injects one known fault and records pass or fail. It is not shipboard commissioning experience.

Field work already on the CV (installation, functional verification, troubleshooting, and service records at the customer's equipment) stays as that work. Do not describe this trainer as time on a vessel or as a certified automation system.
