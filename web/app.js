const message = document.querySelector("#message");
let busy = false;

function hex(value) {
  return `0x${Number(value || 0).toString(16).toUpperCase().padStart(4, "0")}`;
}

function setMessage(text) {
  message.textContent = text || "";
}

async function request(url, options) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail || `Request failed (${response.status})`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

function post(url, body) {
  return request(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : "{}",
  });
}

function setBusy(next) {
  busy = next;
  document.querySelectorAll("button, select").forEach((node) => {
    node.disabled = next;
  });
}

function lamp(node, mode) {
  node.className = `lamp ${mode}`;
}

function renderPump(prefix, pump) {
  if (!pump) return;
  const card = document.querySelector(`#${prefix}-card`);
  const state = document.querySelector(`#${prefix}-state`);
  const button = document.querySelector(`#${prefix}-cmd`);
  const mode = pump.fault ? "fault" : pump.running ? "on" : "idle";
  lamp(card.querySelector(".lamp"), mode);
  const commanded = pump.start_command || pump.auto_demand;
  if (pump.fault && commanded && !pump.running) state.textContent = "Fault — no running feedback";
  else if (pump.fault) state.textContent = "Fault";
  else if (pump.running && pump.auto_demand) state.textContent = "Running on auto";
  else if (pump.running) state.textContent = "Running";
  else if (pump.auto) state.textContent = "Auto — stopped";
  else state.textContent = "Stopped";
  button.textContent = pump.start_command ? "Stop" : "Start";
  button.dataset.start = pump.start_command ? "0" : "1";
  const autoButton = document.querySelector("#pump1-auto");
  if (prefix === "pump1" && autoButton) {
    autoButton.textContent = pump.auto ? "Auto on" : "Auto off";
    autoButton.dataset.auto = pump.auto ? "1" : "0";
  }
}

function renderSnapshot(snap) {
  const link = document.querySelector("#link");
  if (!snap.connected) {
    link.textContent = "NO LINK";
    link.className = "bad";
  } else if (!snap.comms_ok) {
    link.textContent = "HEARTBEAT LOST";
    link.className = "bad";
  } else {
    link.textContent = "ONLINE";
    link.className = "ok";
  }

  const availability = document.querySelector("#availability");
  availability.textContent = snap.availability_percent == null ? "—" : `${snap.availability_percent.toFixed(1)}%`;
  document.querySelector("#downtime").textContent = `${Number(snap.downtime_seconds || 0).toFixed(1)} s`;
  document.querySelector("#heartbeat").textContent = snap.connected ? String(snap.heartbeat) : "—";
  document.querySelector("#io-strip").textContent = snap.connected
    ? `40006 heartbeat ${snap.heartbeat} · 40005 alarm ${hex(snap.alarm_word)} · 40008 ack ${hex(snap.ack_word)}`
    : "Waiting for the PLC image.";

  const list = document.querySelector("#alarm-list");
  if (!snap.alarms.length) {
    list.innerHTML = '<li class="empty">No active alarms</li>';
  } else {
    list.innerHTML = snap.alarms.map((alarm) => `
      <li class="alarm ${alarm.priority} ${alarm.acknowledged ? "ack" : "unack"}">
        <strong>${alarm.name}</strong>
        <span>${alarm.priority} · ${alarm.acknowledged ? "acknowledged" : "unacknowledged"}</span>
      </li>
    `).join("");
  }
  const chips = snap.active_faults || [];
  document.querySelector("#fault-chips").textContent = chips.length
    ? `Injected: ${chips.map((item) => item.label).join(", ")}`
    : "";
  const events = document.querySelector("#event-list");
  if (!snap.events || !snap.events.length) {
    events.innerHTML = '<li class="empty">No events yet</li>';
  } else {
    events.innerHTML = snap.events.map((event) => `<li><time>${event.time}</time>${event.text}</li>`).join("");
  }
  if (!snap.connected) return;

  const tanks = snap.tanks || [];
  tanks.forEach((tank, index) => {
    const number = index + 1;
    const fill = document.querySelector(`#tank${number}-fill`);
    const high = tank.level_percent >= 85;
    fill.style.height = `${Math.max(0, Math.min(100, tank.level_percent))}%`;
    fill.className = high ? "tank-fill high" : "tank-fill";
    document.querySelector(`#tank${number}-value`).textContent = `${tank.level_percent.toFixed(1)}%`;
  });

  const temp = document.querySelector("#temp-value");
  temp.textContent = `${Number(snap.er_temp_c).toFixed(1)} °C`;
  temp.className = snap.er_temp_c >= 70 ? "value hot" : "value";
  const pressure = document.querySelector("#pressure-value");
  pressure.textContent = `${Number(snap.cooling_pressure_bar).toFixed(1)} bar`;
  pressure.className = snap.cooling_pressure_bar <= 2 ? "value hot" : "value";

  renderPump("pump1", snap.pumps[0]);
  renderPump("pump2", snap.pumps[1]);

  const power = [
    ["main", snap.main_power_ok],
    ["emergency", snap.emergency_power_ok],
  ];
  power.forEach(([name, ok]) => {
    lamp(document.querySelector(`#${name}-lamp`), ok ? "on" : "alarm");
    document.querySelector(`#${name}-power-state`).textContent = ok ? "Available" : "Lost";
  });

  document.querySelectorAll(".fire").forEach((card, index) => {
    const active = Boolean(snap.fire_zones[index]);
    lamp(card.querySelector(".lamp"), active ? "alarm" : "idle");
    card.querySelector("p").textContent = active ? "Sensor alarm" : "Normal";
  });
}

function showReport(report) {
  const row = document.querySelector(`#step-${report.id}`);
  if (!row) return;
  const badge = row.querySelector("[data-badge]");
  badge.textContent = report.result === "pass" ? "PASS" : report.result === "fail" ? "FAIL" : "NOT RUN";
  badge.className = `badge ${report.result || "not_run"}`;
  const time = row.querySelector("[data-time]");
  time.textContent = report.response_time_ms == null ? "" : `${report.response_time_ms} ms`;
  row.querySelector("[data-notes]").textContent = report.notes || "";
}

function buildSteps(steps) {
  const root = document.querySelector("#steps");
  root.innerHTML = steps.map((step) => `
    <li id="step-${step.id}">
      <div class="step-top">
        <h3>${step.title}</h3>
        <button type="button" data-run="${step.id}">Run</button>
      </div>
      <p class="expected">${step.expected}</p>
      <p class="outcome"><span class="badge not_run" data-badge>NOT RUN</span><span class="time" data-time></span></p>
      <p class="notes" data-notes></p>
    </li>
  `).join("");
  root.querySelectorAll("[data-run]").forEach((button) => {
    button.addEventListener("click", () => runStep(button.dataset.run));
  });
  steps.forEach(showReport);
}

async function runStep(id) {
  setMessage("");
  setBusy(true);
  const badge = document.querySelector(`#step-${id} [data-badge]`);
  if (badge) {
    badge.textContent = "RUNNING";
    badge.className = "badge running";
  }
  try {
    const report = await post(`/api/commissioning/steps/${id}/run`);
    showReport(report);
    if (report.result === "fail") setMessage(report.notes);
  } catch (error) {
    setMessage(error.message);
  } finally {
    setBusy(false);
  }
}

async function runAll() {
  const buttons = [...document.querySelectorAll("[data-run]")];
  for (const button of buttons) {
    await runStep(button.dataset.run);
    await new Promise((resolve) => setTimeout(resolve, 600));
  }
}

async function poll() {
  try {
    const snap = await request("/api/snapshot");
    renderSnapshot(snap);
  } catch (error) {
    if (!busy) setMessage(error.message);
  }
}

function drawTrend(samples) {
  const svg = document.querySelector("#trend");
  if (!samples.length) {
    svg.innerHTML = "";
    return;
  }
  const width = 640;
  const height = 140;
  const series = [
    { key: "ballast1", color: "#6fd0e6", min: 0, max: 100 },
    { key: "temp", color: "#f0b429", min: 30, max: 90 },
    { key: "pressure", color: "#3ecf8e", min: 0, max: 8 },
  ];
  const step = samples.length === 1 ? 0 : width / (samples.length - 1);
  const lines = series.map((item) => {
    const points = samples.map((sample, index) => {
      const ratio = (sample[item.key] - item.min) / (item.max - item.min);
      const y = height - 8 - Math.max(0, Math.min(1, ratio)) * (height - 16);
      return `${(index * step).toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");
    return `<polyline fill="none" stroke="${item.color}" stroke-width="2" points="${points}" />`;
  }).join("");
  svg.innerHTML = lines;
}

async function pollTrends() {
  try {
    drawTrend(await request("/api/trends"));
  } catch (_error) {
    // The snapshot poll already reports a lost link.
  }
}

document.querySelector("#pump1-cmd").addEventListener("click", async () => {
  const start = document.querySelector("#pump1-cmd").dataset.start !== "0";
  try {
    setMessage("");
    await post("/api/commands", { pump1_start: start });
  } catch (error) {
    setMessage(error.message);
  }
});

document.querySelector("#pump2-cmd").addEventListener("click", async () => {
  const start = document.querySelector("#pump2-cmd").dataset.start !== "0";
  try {
    setMessage("");
    await post("/api/commands", { pump2_start: start });
  } catch (error) {
    setMessage(error.message);
  }
});

document.querySelector("#ack-btn").addEventListener("click", async () => {
  try { await post("/api/alarms/ack"); } catch (error) { setMessage(error.message); }
});

document.querySelector("#reset-btn").addEventListener("click", async () => {
  try { await post("/api/alarms/reset"); } catch (error) { setMessage(error.message); }
});

document.querySelector("#fault-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    setMessage("");
    await post("/api/faults", { id: document.querySelector("#fault").value });
  } catch (error) {
    setMessage(error.message);
  }
});

document.querySelector("#pump1-auto").addEventListener("click", async () => {
  const turnOn = document.querySelector("#pump1-auto").dataset.auto !== "1";
  try {
    setMessage("");
    await post("/api/commands", { pump1_auto: turnOn });
  } catch (error) {
    setMessage(error.message);
  }
});

document.querySelector("#export-report").addEventListener("click", async () => {
  try {
    const response = await fetch("/api/commissioning/report");
    if (!response.ok) throw new Error("Could not build the commissioning report");
    const blob = await response.blob();
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "commissioning-report.txt";
    link.click();
    URL.revokeObjectURL(link.href);
  } catch (error) {
    setMessage(error.message);
  }
});

document.querySelector("#run-all").addEventListener("click", () => {
  runAll().catch((error) => setMessage(error.message));
});

async function init() {
  const [faults, steps] = await Promise.all([
    request("/api/faults"),
    request("/api/commissioning/steps"),
  ]);
  const select = document.querySelector("#fault");
  select.innerHTML = `<option value="none">Clear injected faults</option>${
    faults.map((item) => `<option value="${item.id}">${item.label}</option>`).join("")
  }`;
  buildSteps(steps);
  await poll();
  await pollTrends();
  setInterval(() => { poll(); }, 500);
  setInterval(() => { pollTrends(); }, 1000);
}

init().catch((error) => setMessage(error.message));
