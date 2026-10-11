"""HTTP API in front of the Modbus plant simulator."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from api.supervisor import BusyError, StepError, Supervisor
from common.map import FAULT_BY_ID, FAULTS

WEB = Path(__file__).resolve().parent.parent / "web"
supervisor = Supervisor()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await supervisor.start()
    yield
    await supervisor.stop()


app = FastAPI(
    title="Marine Auxiliary Commissioning Trainer",
    description=(
        "SCADA API for a simulated vessel engine room. "
        "Process values are read and written only over Modbus TCP."
    ),
    version="1.0.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=WEB), name="static")


class FaultIn(BaseModel):
    id: str


class CommandIn(BaseModel):
    pump1_start: bool | None = None
    pump2_start: bool | None = None
    pump1_auto: bool | None = None


def _call_error(exc: Exception) -> HTTPException:
    if isinstance(exc, BusyError):
        return HTTPException(status_code=409, detail="A commissioning step is already running")
    if isinstance(exc, (StepError, ConnectionError)):
        return HTTPException(status_code=503, detail=str(exc))
    raise exc


@app.get("/")
async def index():
    return FileResponse(WEB / "index.html")


@app.get("/api/health")
async def health():
    snap = await supervisor.snapshot()
    return {"status": "ok", "plc_connected": snap["connected"]}


@app.get("/api/snapshot")
async def snapshot():
    return await supervisor.snapshot()


@app.get("/api/tags")
async def tags():
    return supervisor.tag_list()


@app.get("/api/alarms")
async def alarms():
    snap = await supervisor.snapshot()
    return snap["alarms"]


@app.post("/api/alarms/ack")
async def acknowledge():
    try:
        await supervisor.acknowledge()
    except (BusyError, StepError, ConnectionError) as exc:
        raise _call_error(exc) from exc
    return await supervisor.snapshot()


@app.post("/api/alarms/reset")
async def reset_alarms():
    try:
        await supervisor.reset()
    except (BusyError, StepError, ConnectionError) as exc:
        raise _call_error(exc) from exc
    return await supervisor.snapshot()


@app.get("/api/availability")
async def availability():
    snap = await supervisor.snapshot()
    return {
        "comms_ok": snap["comms_ok"],
        "availability_percent": snap["availability_percent"],
        "downtime_seconds": snap["downtime_seconds"],
        "heartbeat": snap["heartbeat"],
    }


@app.get("/api/faults")
async def list_faults():
    return [{"id": item["id"], "label": item["label"]} for item in FAULTS]


@app.post("/api/faults")
async def inject_fault(body: FaultIn):
    if body.id != "none" and body.id not in FAULT_BY_ID:
        raise HTTPException(status_code=400, detail="Unknown fault id")
    try:
        await supervisor.inject(body.id)
    except (BusyError, StepError, ConnectionError) as exc:
        raise _call_error(exc) from exc
    return await supervisor.snapshot()


@app.post("/api/commands")
async def commands(body: CommandIn):
    try:
        await supervisor.set_commands(body.pump1_start, body.pump2_start, body.pump1_auto)
    except (BusyError, StepError, ConnectionError) as exc:
        raise _call_error(exc) from exc
    return await supervisor.snapshot()


@app.get("/api/trends")
async def trends():
    return supervisor.trends()


@app.get("/api/commissioning/report")
async def commissioning_report():
    return PlainTextResponse(
        supervisor.report_text(),
        headers={"Content-Disposition": "attachment; filename=commissioning-report.txt"},
    )


@app.get("/api/commissioning/steps")
async def commissioning_steps():
    return supervisor.steps()


@app.post("/api/commissioning/steps/{step_id}/run")
async def run_commissioning_step(step_id: str):
    try:
        return await supervisor.run_step(step_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown commissioning step") from None
    except BusyError as exc:
        raise _call_error(exc) from exc


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
