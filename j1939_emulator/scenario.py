"""Scenarios: timed steps (driving, ramps, faults) that the emulator plays by itself.

A scenario is a TOML file:

    name = "Drive and stop"
    description = "..."

    [[step]]
    at = "0s"
    ignition = "run"

    [[step]]
    at = "5s"
    ramp = { speed_mph = 35, rpm = 1400, over = "20s" }

`at` is the time from the start of the scenario. Each step may hold several actions; they
run in a fixed order (ignition, rpm, speed, ramp, meters, VIN, DTCs, faults, note). The
whole file is checked when it is loaded, so a typo fails at once, not in the middle of a
test. Times are real time: the ELD runs on its own clock, so nothing can be sped up.
"""

from __future__ import annotations

import re
import threading
import time
import tomllib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from j1939_emulator.diagnostics import parse_dtc_key
from j1939_emulator.ecu_identity import validate_vin
from j1939_emulator.faults import (
    BROADCAST_PGNS,
    MAX_REQUEST_DELAY_MS,
    REQ_DELAY,
    REQUEST_MODES,
    REQUEST_TARGET_ALL,
)
from j1939_emulator.meters_store import state_file
from j1939_emulator.pgn import (
    OVERRIDABLE_SPNS,
    SPN_ERROR,
    SPN_NORMAL,
    SPN_NOT_AVAILABLE,
)

BUILTIN_DIR = Path(__file__).parent / "scenarios"
USER_DIR_NAME = "scenarios"
TICK_S = 0.05  # ramp resolution: 20 updates a second (CCVS goes out every 100 ms)
MAX_RPM = 8000.0  # J1939 SPN 190 tops out at 8031.875 rpm
MAX_SPEED_MPH = 155.0  # SPN 84 tops out at 250.996 km/h
CURVES = ("smooth", "linear")

_TOP_KEYS = {"name", "description", "clear_faults_on_end", "restore_vin_on_end", "step"}
_STEP_KEYS = {
    "at", "ignition", "rpm", "speed_mph", "ramp", "odometer_mi", "odometer_add_mi",
    "engine_hours", "engine_hours_add", "vin", "dtc", "fault", "clear_faults", "note",
}
_RAMP_KEYS = {"speed_mph", "rpm", "over", "curve"}
_FAULT_KEYS = (
    {"silent", "requests", "freeze_odometer", "freeze_hours"}
    | set(BROADCAST_PGNS) | set(OVERRIDABLE_SPNS)
)
_REQUEST_KEYS = {"mode", "pgn", "delay"}
_SPN_MODE_ALIASES = {
    "normal": SPN_NORMAL, "real": SPN_NORMAL,
    "not_available": SPN_NOT_AVAILABLE, "not available": SPN_NOT_AVAILABLE,
    "na": SPN_NOT_AVAILABLE, "error": SPN_ERROR,
}
_PGN_ALIASES = {"all": REQUEST_TARGET_ALL, "vin": 65260}
_DURATION_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(ms|h|m|s)")


class ScenarioError(ValueError):
    """The scenario file is not valid; the message says where and why."""


def parse_duration(value: Any) -> float:
    """Seconds from 5, 2.5, "500ms", "20s", "1m30s", "2h"."""
    if isinstance(value, bool):
        raise ValueError(f"not a duration: {value!r}")
    if isinstance(value, (int, float)):
        if value < 0:
            raise ValueError(f"negative duration: {value!r}")
        return float(value)
    if not isinstance(value, str):
        raise ValueError(f"not a duration: {value!r}")
    text = value.strip().lower().replace(" ", "")
    pos, total = 0, 0.0
    for m in _DURATION_RE.finditer(text):
        if m.start() != pos:
            break
        num, unit = float(m.group(1)), m.group(2)
        total += num * {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}[unit]
        pos = m.end()
    if pos != len(text) or not text:
        raise ValueError(f"not a duration: {value!r} (use e.g. 500ms, 20s, 1m30s, 2h)")
    return total


def format_time(seconds: float) -> str:
    """0:05, 1:30, 1:02:03; tenths when a step is not on a whole second (0:00.5)."""
    s = max(0.0, seconds)
    whole = int(s + 1e-6)
    frac = s - whole
    h, rem = divmod(whole, 3600)
    m, sec = divmod(rem, 60)
    text = f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"
    if frac > 0.05:
        text += f".{int(round(frac * 10)) % 10}"
    return text


def _secs(seconds: float) -> str:
    """Short duration for step text: 500 ms, 20 s, 1 min 30 s."""
    if seconds < 1:
        return f"{seconds * 1000:.0f} ms"
    if seconds < 60:
        return f"{seconds:g} s"
    m, s = divmod(int(round(seconds)), 60)
    return f"{m} min {s} s" if s else f"{m} min"


@dataclass
class Ramp:
    over: float
    curve: str = "smooth"
    speed_mph: float | None = None
    rpm: float | None = None


@dataclass
class Step:
    index: int  # 1-based, in time order
    at: float
    ignition: bool | None = None  # True = engine running, False = key ON / engine off
    rpm: float | None = None
    speed_mph: float | None = None
    ramp: Ramp | None = None
    odometer_mi: float | None = None
    odometer_add_mi: float | None = None
    engine_hours: float | None = None
    engine_hours_add: float | None = None
    vin: str | None = None
    dtc: dict[str, bool] = field(default_factory=dict)
    fault: dict[str, Any] = field(default_factory=dict)
    clear_faults: bool = False
    note: str = ""

    @property
    def end(self) -> float:
        return self.at + (self.ramp.over if self.ramp else 0.0)

    def describe(self) -> list[str]:
        """What the step does, one short line per action (GUI step list and trace)."""
        out: list[str] = []
        if self.ignition is not None:
            out.append("Ignition: engine running" if self.ignition else "Ignition: key ON, engine off")
        if self.rpm is not None:
            out.append(f"Engine speed {self.rpm:g} rpm")
        if self.speed_mph is not None:
            out.append(f"Vehicle speed {self.speed_mph:g} mph")
        if self.ramp is not None:
            parts = []
            if self.ramp.speed_mph is not None:
                parts.append(f"speed → {self.ramp.speed_mph:g} mph")
            if self.ramp.rpm is not None:
                parts.append(f"rpm → {self.ramp.rpm:g}")
            curve = "" if self.ramp.curve == "smooth" else f" ({self.ramp.curve})"
            out.append(f"{', '.join(parts).capitalize()} over {_secs(self.ramp.over)}{curve}")
        if self.odometer_mi is not None:
            out.append(f"Odometer = {self.odometer_mi:g} mi")
        if self.odometer_add_mi is not None:
            out.append(f"Odometer {self.odometer_add_mi:+g} mi")
        if self.engine_hours is not None:
            out.append(f"Engine hours = {self.engine_hours:g} h")
        if self.engine_hours_add is not None:
            out.append(f"Engine hours {self.engine_hours_add:+g} h")
        if self.vin is not None:
            out.append(f"VIN → {self.vin}")
        for key, on in self.dtc.items():
            spn, fmi = parse_dtc_key(key)
            out.append(f"DTC SPN {spn} / FMI {fmi} {'active' if on else 'cleared'}")
        f = self.fault
        if "silent" in f:
            out.append(f"Fault: ECU silent {'ON' if f['silent'] else 'OFF'}")
        for key, (acronym, _pgn) in BROADCAST_PGNS.items():
            if key in f:
                out.append(f"Fault: {acronym} broadcast {'ON' if f[key] else 'OFF'}")
        for key, (spn, _p) in OVERRIDABLE_SPNS.items():
            if key in f:
                mode = f[key]
                out.append(
                    f"SPN {spn} back to real value" if mode == SPN_NORMAL
                    else f"Fault: SPN {spn} sends {mode.replace('_', ' ')}"
                )
        if "requests" in f:
            mode, target, delay_ms = f["requests"]
            what = "all PGNs" if target == REQUEST_TARGET_ALL else f"PGN {target}"
            extra = f" {_secs(delay_ms / 1000)}" if mode == REQ_DELAY else ""
            out.append(f"Requests for {what}: {mode}{extra}")
        for key, label in (("freeze_odometer", "odometer"), ("freeze_hours", "engine hours")):
            if key in f:
                out.append(f"{'Freeze' if f[key] else 'Unfreeze'} {label}")
        if self.clear_faults:
            out.append("Clear all faults")
        if self.note:
            out.append(f"“{self.note}”")
        return out


@dataclass
class Scenario:
    name: str
    steps: list[Step]
    description: str = ""
    clear_faults_on_end: bool = True
    path: Path | None = None
    restore_vin_on_end: bool = False  # put back the VIN the ECU had when the scenario started

    @property
    def duration(self) -> float:
        return max((s.end for s in self.steps), default=0.0)


# --- loading and checking ---


def _num(where: str, key: str, value: Any, lo: float, hi: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ScenarioError(f"{where}: {key} must be a number, got {value!r}")
    if not lo <= value <= hi:
        raise ScenarioError(f"{where}: {key} = {value} is out of range {lo:g}…{hi:g}")
    return float(value)


def _flag(where: str, key: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise ScenarioError(f"{where}: {key} must be true or false, got {value!r}")
    return value


def _table(where: str, key: str, value: Any, allowed: set[str]) -> dict:
    if not isinstance(value, dict):
        raise ScenarioError(f"{where}: {key} must be a table, e.g. {key} = {{ ... }}")
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ScenarioError(
            f"{where}: unknown key {key}.{unknown[0]} (allowed: {', '.join(sorted(allowed))})"
        )
    return value


def _parse_requests(where: str, raw: Any) -> tuple[str, int, int]:
    raw = _table(where, "fault.requests", raw, _REQUEST_KEYS)
    mode = raw.get("mode")
    if mode not in REQUEST_MODES:
        raise ScenarioError(
            f"{where}: fault.requests.mode must be one of {', '.join(REQUEST_MODES)}, got {mode!r}"
        )
    pgn = raw.get("pgn", "all")
    if isinstance(pgn, str):
        if pgn.lower() not in _PGN_ALIASES:
            raise ScenarioError(f"{where}: fault.requests.pgn must be a PGN number, \"all\" or \"vin\"")
        target = _PGN_ALIASES[pgn.lower()]
    elif isinstance(pgn, int) and not isinstance(pgn, bool) and 0 <= pgn <= 0x3FFFF:
        target = pgn
    else:
        raise ScenarioError(f"{where}: fault.requests.pgn must be a PGN number, \"all\" or \"vin\"")
    try:
        delay_ms = round(parse_duration(raw.get("delay", "500ms")) * 1000)
    except ValueError as exc:
        raise ScenarioError(f"{where}: fault.requests.delay: {exc}") from None
    if delay_ms > MAX_REQUEST_DELAY_MS:
        raise ScenarioError(f"{where}: fault.requests.delay is above {MAX_REQUEST_DELAY_MS // 1000} s")
    return mode, target, delay_ms


def _parse_step(where: str, raw: Any) -> Step:
    if not isinstance(raw, dict):
        raise ScenarioError(f"{where}: must be a table ([[step]])")
    unknown = sorted(set(raw) - _STEP_KEYS)
    if unknown:
        raise ScenarioError(f"{where}: unknown key {unknown[0]!r} (allowed: {', '.join(sorted(_STEP_KEYS))})")
    if "at" not in raw:
        raise ScenarioError(f"{where}: missing at = \"…\" (time from the start, e.g. at = \"1m30s\")")
    try:
        at = parse_duration(raw["at"])
    except ValueError as exc:
        raise ScenarioError(f"{where}: at: {exc}") from None
    step = Step(index=0, at=at)

    if "ignition" in raw:
        value = str(raw["ignition"]).lower()
        if value not in ("run", "on"):
            raise ScenarioError(f"{where}: ignition must be \"run\" (engine running) or \"on\" (key ON, engine off)")
        step.ignition = value == "run"
    if "rpm" in raw:
        step.rpm = _num(where, "rpm", raw["rpm"], 0, MAX_RPM)
    if "speed_mph" in raw:
        step.speed_mph = _num(where, "speed_mph", raw["speed_mph"], 0, MAX_SPEED_MPH)
    if "ramp" in raw:
        r = _table(where, "ramp", raw["ramp"], _RAMP_KEYS)
        if "over" not in r:
            raise ScenarioError(f"{where}: ramp needs over = \"…\" (how long, e.g. over = \"20s\")")
        try:
            over = parse_duration(r["over"])
        except ValueError as exc:
            raise ScenarioError(f"{where}: ramp.over: {exc}") from None
        if over <= 0:
            raise ScenarioError(f"{where}: ramp.over must be longer than 0")
        curve = r.get("curve", "smooth")
        if curve not in CURVES:
            raise ScenarioError(f"{where}: ramp.curve must be \"smooth\" or \"linear\"")
        ramp = Ramp(over=over, curve=curve)
        if "speed_mph" in r:
            ramp.speed_mph = _num(where, "ramp.speed_mph", r["speed_mph"], 0, MAX_SPEED_MPH)
        if "rpm" in r:
            ramp.rpm = _num(where, "ramp.rpm", r["rpm"], 0, MAX_RPM)
        if ramp.speed_mph is None and ramp.rpm is None:
            raise ScenarioError(f"{where}: ramp needs speed_mph and / or rpm")
        step.ramp = ramp
    for key in ("odometer_mi", "engine_hours"):
        if key in raw:
            setattr(step, key, _num(where, key, raw[key], 0, 9_999_999))
    for key in ("odometer_add_mi", "engine_hours_add"):
        if key in raw:
            setattr(step, key, _num(where, key, raw[key], -9_999_999, 9_999_999))
    if "vin" in raw:
        try:
            step.vin = validate_vin(str(raw["vin"]))
        except ValueError as exc:
            raise ScenarioError(f"{where}: vin: {exc}") from None
    if "dtc" in raw:
        d = raw["dtc"]
        if not isinstance(d, dict):
            raise ScenarioError(f"{where}: dtc must be a table, e.g. dtc = {{ spn110_fmi3 = true }}")
        for k in d:
            try:
                parse_dtc_key(k)
            except ValueError as exc:
                raise ScenarioError(f"{where}: dtc: {exc}") from None
        step.dtc = {k.lower(): _flag(where, f"dtc.{k}", v) for k, v in d.items()}
    if "fault" in raw:
        f = _table(where, "fault", raw["fault"], _FAULT_KEYS)
        parsed: dict[str, Any] = {}
        for key, value in f.items():
            if key in OVERRIDABLE_SPNS:
                mode = _SPN_MODE_ALIASES.get(str(value).lower())
                if mode is None:
                    raise ScenarioError(
                        f"{where}: fault.{key} must be \"normal\", \"not_available\" or \"error\""
                    )
                parsed[key] = mode
            elif key == "requests":
                parsed[key] = _parse_requests(where, value)
            else:
                parsed[key] = _flag(where, f"fault.{key}", value)
        step.fault = parsed
    if "clear_faults" in raw:
        step.clear_faults = _flag(where, "clear_faults", raw["clear_faults"])
    if "note" in raw:
        step.note = str(raw["note"]).strip()
    if not step.describe():
        raise ScenarioError(f"{where}: the step does nothing (add an action or a note)")
    return step


def parse_scenario(raw: dict, path: Path | None = None) -> Scenario:
    unknown = sorted(set(raw) - _TOP_KEYS)
    if unknown:
        raise ScenarioError(f"unknown top-level key {unknown[0]!r} (allowed: {', '.join(sorted(_TOP_KEYS))})")
    steps_raw = raw.get("step")
    if not isinstance(steps_raw, list) or not steps_raw:
        raise ScenarioError("no steps: add at least one [[step]]")
    steps = [_parse_step(f"step {i}", s) for i, s in enumerate(steps_raw, start=1)]
    steps.sort(key=lambda s: s.at)  # stable: steps at the same time keep the file order
    for i, s in enumerate(steps, start=1):
        s.index = i
    flags = {}
    for key, default in (("clear_faults_on_end", True), ("restore_vin_on_end", False)):
        flags[key] = raw.get(key, default)
        if not isinstance(flags[key], bool):
            raise ScenarioError(f"{key} must be true or false")
    name = str(raw.get("name") or (path.stem if path else "Scenario"))
    return Scenario(
        name, steps, str(raw.get("description", "")).strip(),
        clear_faults_on_end=flags["clear_faults_on_end"], path=path,
        restore_vin_on_end=flags["restore_vin_on_end"],
    )


def load_scenario(path: str | Path) -> Scenario:
    path = Path(path)
    try:
        with open(path, "rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ScenarioError(f"{path.name}: not valid TOML: {exc}") from None
    except OSError as exc:
        raise ScenarioError(f"{path.name}: {exc}") from None
    try:
        return parse_scenario(raw, path)
    except ScenarioError as exc:
        raise ScenarioError(f"{path.name}: {exc}") from None


def user_dir() -> Path:
    """Folder for the user's own scenarios (and ones uploaded in the GUI)."""
    return state_file().parent / USER_DIR_NAME


def list_scenarios() -> list[tuple[str, Path]]:
    """(label, path) of the built-in scenarios, then the user's; sorted by file name."""
    out: list[tuple[str, Path]] = []
    for folder, prefix in ((BUILTIN_DIR, "Built-in"), (user_dir(), "My")):
        try:
            files = sorted(folder.glob("*.toml"))
        except OSError:
            continue
        out.extend((f"{prefix}: {p.stem}", p) for p in files)
    return out


def find_scenario(name: str) -> Path:
    """A path, or the stem of a built-in / user scenario ("drive-and-stop")."""
    p = Path(name)
    if p.suffix == ".toml" and p.exists():
        return p
    for _label, path in list_scenarios():
        if path.stem == name or path.name == name:
            return path
    raise ScenarioError(f"scenario not found: {name!r} (see: scenario list)")


# --- playing ---


class RunState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    FINISHED = "finished"
    STOPPED = "stopped"
    FAILED = "failed"


def _ease(f: float, curve: str) -> float:
    """Fraction of the way at time fraction f: smooth = gentle start and end, like a real truck."""
    f = min(1.0, max(0.0, f))
    return f * f * (3 - 2 * f) if curve == "smooth" else f


@dataclass
class _ActiveRamp:
    start: float
    target: float
    t0: float
    over: float
    curve: str


class ScenarioRunner:
    """Plays one scenario at a time on a running session, in its own thread.

    Steps fire when the scenario clock (paused time excluded) reaches their `at`. Ramps
    update 20 times a second. When it ends (finished, stopped, ECU stopped or an error)
    faults are cleared unless the scenario says clear_faults_on_end = false; the signals
    stay where the scenario left them.
    """

    def __init__(self, session) -> None:
        self.session = session
        self.scenario: Scenario | None = None
        self.state = RunState.IDLE
        self.error = ""
        self.done = 0  # steps already run
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._elapsed_before = 0.0  # scenario seconds before the current RUNNING stretch
        self._resumed_at = 0.0  # monotonic start of the current RUNNING stretch
        self._ramps: dict[str, _ActiveRamp] = {}
        self._vin_at_start = ""

    @property
    def active(self) -> bool:
        return self.state in (RunState.RUNNING, RunState.PAUSED)

    def elapsed(self) -> float:
        with self._lock:
            if self.state is RunState.RUNNING:
                return self._elapsed_before + time.monotonic() - self._resumed_at
            return self._elapsed_before

    def start(self, scenario: Scenario) -> None:
        if not self.session.running:
            raise RuntimeError("Press START first: the ECU is not running")
        self.stop()
        with self._lock:
            self.scenario = scenario
            self.state = RunState.RUNNING
            self.error = ""
            self.done = 0
            self._ramps = {}
            self._elapsed_before = 0.0
            self._resumed_at = time.monotonic()
            self._stop = threading.Event()
            self._vin_at_start = self.session.identity.vin
        self.session.note(
            f"SCENARIO {scenario.name!r} started: {len(scenario.steps)} steps, "
            f"{format_time(scenario.duration)}"
        )
        self._thread = threading.Thread(target=self._run, name="scenario", daemon=True)
        self._thread.start()

    def pause(self) -> None:
        with self._lock:
            if self.state is not RunState.RUNNING:
                return
            self._elapsed_before = self.elapsed()
            self.state = RunState.PAUSED
        self.session.note(f"SCENARIO paused at {format_time(self._elapsed_before)}")

    def resume(self) -> None:
        with self._lock:
            if self.state is not RunState.PAUSED:
                return
            self._resumed_at = time.monotonic()
            self.state = RunState.RUNNING
        self.session.note(f"SCENARIO resumed at {format_time(self._elapsed_before)}")

    def stop(self) -> None:
        """Stop the scenario (not the ECU); waits for its thread."""
        thread = self._thread
        if thread is None:
            return
        self._stop.set()
        if thread is not threading.current_thread():
            thread.join(timeout=3.0)
        self._thread = None

    # --- thread ---

    def _run(self) -> None:
        scenario = self.scenario
        assert scenario is not None
        end_state, reason = RunState.FINISHED, ""
        try:
            while True:
                if self._stop.wait(TICK_S):
                    end_state, reason = RunState.STOPPED, "stopped"
                    break
                if not self.session.running:
                    end_state, reason = RunState.FAILED, "the ECU was stopped"
                    break
                if self.state is RunState.PAUSED:
                    continue
                t = self.elapsed()
                while self.done < len(scenario.steps) and scenario.steps[self.done].at <= t:
                    step = scenario.steps[self.done]
                    self._apply(step, t)
                    self.done += 1
                self._advance_ramps(t)
                if self.done >= len(scenario.steps) and not self._ramps:
                    break
        except Exception as exc:  # a step the session refused: stop rather than carry on wrongly
            end_state, reason = RunState.FAILED, f"step {self.done + 1}: {exc}"
        with self._lock:
            self._elapsed_before = self.elapsed()
            self._ramps = {}
            # Clock frozen and still "active" while cleaning up, so nobody sees the end
            # state before the faults are cleared and the VIN is back.
            self.state = RunState.PAUSED
        tail = f": {reason}" if reason and end_state is not RunState.STOPPED else ""
        self.session.note(
            f"SCENARIO {scenario.name!r} {end_state.value} at {format_time(self._elapsed_before)}{tail}"
        )
        try:
            if scenario.clear_faults_on_end:
                self.session.clear_faults()
            if scenario.restore_vin_on_end and self.session.identity.vin != self._vin_at_start:
                self.session.set_vin(self._vin_at_start)
                self.session.note(f"SCENARIO VIN restored to {self._vin_at_start}")
        finally:
            with self._lock:
                self.state = end_state
                self.error = reason if end_state is RunState.FAILED else ""

    def _apply(self, step: Step, t: float) -> None:
        s, session = self.session.signals, self.session
        session.note(f"SCENARIO step {step.index} @{format_time(step.at)}: {'; '.join(step.describe())}")
        if step.ignition is not None:
            self._ramps.pop("rpm", None)
            s.set_ignition(step.ignition, notify=False)
        if step.rpm is not None:
            self._ramps.pop("rpm", None)
            s.set_engine_speed(step.rpm, notify=False)
        if step.speed_mph is not None:
            self._ramps.pop("speed", None)
            s.spn84_speed_mph = step.speed_mph
        if step.ramp is not None:
            r = step.ramp
            # Starts where the value is now, from the step's own time (not from a late tick).
            if r.speed_mph is not None:
                self._ramps["speed"] = _ActiveRamp(s.spn84_speed_mph, r.speed_mph, step.at, r.over, r.curve)
            if r.rpm is not None:
                self._ramps["rpm"] = _ActiveRamp(s.spn190_rpm, r.rpm, step.at, r.over, r.curve)
        if step.odometer_mi is not None:
            s.spn245_total_mi = step.odometer_mi
        if step.odometer_add_mi is not None:
            s.spn245_total_mi = max(0.0, s.spn245_total_mi + step.odometer_add_mi)
        if step.engine_hours is not None:
            s.spn247_engine_hours = step.engine_hours
        if step.engine_hours_add is not None:
            s.spn247_engine_hours = max(0.0, s.spn247_engine_hours + step.engine_hours_add)
        if step.vin is not None:
            session.set_vin(step.vin)
        if step.dtc:
            try:
                session.set_dtcs(step.dtc)
            except KeyError as exc:
                session.note(f"SCENARIO step skipped DTCs: {exc.args[0]}")
        f = step.fault
        if "silent" in f:
            session.set_silent(f["silent"])
        for key in BROADCAST_PGNS:
            if key in f:
                session.set_pgn_enabled(key, f[key])
        for key in OVERRIDABLE_SPNS:
            if key in f:
                session.set_spn_override(key, f[key])
        if "requests" in f:
            mode, target, delay_ms = f["requests"]
            session.set_request_fault(mode, target=target, delay_ms=delay_ms)
        if "freeze_odometer" in f:
            session.set_freeze(odometer=f["freeze_odometer"])
        if "freeze_hours" in f:
            session.set_freeze(hours=f["freeze_hours"])
        if step.clear_faults:
            session.clear_faults()

    def _advance_ramps(self, t: float) -> None:
        s = self.session.signals
        for name, r in list(self._ramps.items()):
            frac = (t - r.t0) / r.over
            value = r.start + (r.target - r.start) * _ease(frac, r.curve)
            if frac >= 1.0:
                value = r.target
                del self._ramps[name]
            # Whole rpm and 0.01 mph: finer than any ELD shows, and tidy in the GUI.
            if name == "speed":
                s.spn84_speed_mph = round(value, 2)
            else:
                s.set_engine_speed(round(value), notify=False)
