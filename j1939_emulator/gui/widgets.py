"""Reusable SPN control widgets for the NiceGUI Signals tab."""

from __future__ import annotations

import json
import time
from typing import Any, Callable

from nicegui import ui

from j1939_emulator.bus.trace import (
    TRAFFIC_ROWS,
    TrafficEntry,
    decode,
    pgn_name,
    split_id,
    trace_dir,
)
from j1939_emulator.ecu_identity import generate_vin, vin_check_digit_warning
from j1939_emulator.pgn import (
    SignalState,
    encode_ccvs,
    encode_eec1,
    encode_hours,
    encode_vd,
    payload_hex,
)


def _fmt_value(v: float, decimals: int | None) -> str:
    if decimals is not None:
        return f"{v:.{decimals}f}"
    return str(int(v)) if v == int(v) else str(v)


def _signal_label(spn: str, name: str) -> None:
    """SPN and parameter name, each in its own grid column; the name is never cut."""
    with ui.element("div").classes("sig-spn"):
        ui.label(spn).classes("spn-badge font-mono")
    ui.label(name).classes("signal-name")


def _signal_value(unit: str, initial: float, decimals: int | None) -> Any:
    """The current value, the most prominent thing in the row."""
    with ui.element("div").classes("sig-value"):
        disp = ui.label(_fmt_value(float(initial), decimals)).classes("signal-big font-mono")
        ui.label(unit).classes("signal-unit")
    return disp


def slider_spn(
    spn: str,
    name: str,
    unit: str,
    initial: float,
    min_v: float,
    max_v: float,
    step: float,
    on_change: Callable[[float], None],
    presets: list[tuple[str, float]] | None = None,
    decimals: int | None = None,
    number_step: float | None = None,
) -> Any:
    with ui.element("div").classes("signal-box sig-row"):
        _signal_label(spn, name)
        disp = _signal_value(unit, initial, decimals)
        controls = ui.element("div").classes("sig-controls")
        with controls:
            # Input first, so it sits in the same place as the meters' input in every card.
            num = ui.number(
                value=initial,
                min=min_v,
                max=max_v,
                step=number_step if number_step is not None else step,
            ).props("dense outlined").classes("value-input compact-input font-mono")
            slider = ui.slider(min=min_v, max=max_v, step=step, value=initial).props(
                "thumb-size=14px track-size=3px"
            ).classes("range-slider").tooltip(f"Range {min_v:g} – {max_v:g} {unit}")

        syncing = False

        def show(num_v: float) -> None:
            slider.value = num_v
            num.value = num_v
            disp.set_text(_fmt_value(num_v, decimals))

        def apply(val) -> None:
            if syncing:
                return
            try:
                num_v = float(val)
            except (TypeError, ValueError):
                return
            num_v = max(min_v, min(max_v, num_v))
            show(num_v)
            on_change(num_v)

        def sync(val: float) -> None:
            """Reflect a value changed outside the UI without calling on_change."""
            nonlocal syncing
            syncing = True
            try:
                show(max(min_v, min(max_v, float(val))))
            finally:
                syncing = False

        slider.on_value_change(lambda e: apply(e.value))
        num.on_value_change(lambda e: apply(e.value))

        if presets:
            with controls, ui.element("div").classes("preset-group font-mono"):
                for label, val in presets:
                    ui.button(label, on_click=lambda v=val: apply(v)).classes(
                        "preset-btn"
                    ).props("flat dense")
    return sync


def counter_spn(
    spn: str,
    name: str,
    unit: str,
    initial: float,
    max_v: float,
    decimals: int,
    on_change: Callable[[float], None],
    steps: tuple[float, ...],
    hint: str = "",
) -> Any:
    """A meter (odometer, engine hours): exact number entry plus +/- step buttons, no slider."""
    with ui.element("div").classes("signal-box sig-row"):
        _signal_label(spn, name)
        disp = _signal_value(unit, initial, decimals)
        current = [float(initial)]
        syncing = False
        with ui.element("div").classes("sig-controls"):
            num = ui.number(
                value=initial, min=0, max=max_v, step=10 ** -decimals, format=f"%.{decimals}f"
            ).props("dense outlined").classes("counter-input compact-input font-mono")
            with ui.element("div").classes("step-group font-mono"):
                for step in (*(-s for s in reversed(steps)), *steps):
                    ui.button(
                        f"{step:+g}", on_click=lambda d=step: apply(current[0] + d), color=None
                    ).classes("step-btn").props("flat dense")
            if hint:
                ui.icon("info_outline").classes("sig-hint").tooltip(hint)

        def show(v: float) -> None:
            current[0] = v
            num.value = round(v, decimals)
            disp.set_text(_fmt_value(v, decimals))

        def apply(val) -> None:
            if syncing:
                return
            try:
                v = float(val)
            except (TypeError, ValueError):
                return
            v = max(0.0, min(max_v, v))
            show(v)
            on_change(v)

        def sync(val: float) -> None:
            """Reflect a value changed outside the UI without calling on_change."""
            nonlocal syncing
            syncing = True
            try:
                show(max(0.0, min(max_v, float(val))))
            finally:
                syncing = False

        num.on_value_change(lambda e: apply(e.value))
    return sync


def pgn_header(
    acronym: str,
    title: str,
    pgn: int,
    can_id: int,
    cycle_ms: int,
    on_cycle: Callable[[int], None],
    enabled: bool,
) -> tuple[Any, Any]:
    """One-line group header (acronym, name, PGN, ON/OFF, Details) and its collapsible panel.

    Returns (details panel, header badge slot) so callers can add more details (payload)
    and status chips (engine off).
    """
    with ui.element("div").classes("pgn-header"):
        with ui.element("div").classes("pgn-title-group"):
            ui.label(acronym).classes("badge-acronym font-mono")
            ui.label(title).classes("pgn-name").tooltip(title)
            ui.label(f"PGN {pgn}").classes("pgn-number font-mono")
        with ui.element("div").classes("pgn-header-right"):
            badges = ui.element("div").classes("pgn-badges")
            # Broadcast on/off comes from the config ("enabled" in the PGN's section) and is
            # read on START; shown here, not switchable, so the TX logic stays as it is.
            ui.label("● ON" if enabled else "○ OFF").classes(
                "pgn-state font-mono " + ("on" if enabled else "off")
            ).tooltip(
                "Broadcast enabled" if enabled
                else "Broadcast disabled in the config (enabled = false); takes effect on START"
            )
            details_btn = ui.button("Details", icon="expand_more").classes(
                "details-btn font-mono"
            ).props("flat dense no-caps")

    details = ui.element("div").classes("pgn-details")
    with details:
        with ui.element("div").classes("pgn-details-row font-mono"):
            with ui.row().classes("items-center gap-2"):
                ui.label(f"PGN {pgn} (0x{pgn:06X})").classes("badge-subtle font-mono")
                ui.label(f"CAN ID: 0x{can_id:08X}").classes("badge-subtle font-mono").style(
                    "background:#F1F5F9;color:#5B6775;border-color:#CBD5E1;"
                )
            with ui.row().classes("items-center gap-2").style("font-size:11px;color:#5B6775;"):
                ui.label("Cycle:")
                cycle_input = ui.number(value=cycle_ms, min=1, max=60000, step=1).props(
                    "dense outlined"
                ).classes("compact-input").style("width:80px")
                ui.label("ms").style("font-weight:700;color:#1F2A37;")

                def apply_cycle(e) -> None:
                    try:
                        ms = int(float(e.value))
                    except (TypeError, ValueError):
                        return
                    ms = max(1, min(60000, ms))
                    cycle_input.value = ms
                    on_cycle(ms)

                cycle_input.on_value_change(apply_cycle)
    details.set_visibility(False)

    def toggle_details() -> None:
        shown = not details.visible
        details.set_visibility(shown)
        details_btn.props(f"icon={'expand_less' if shown else 'expand_more'}")

    details_btn.on_click(toggle_details)
    return details, badges


def payload_strip(priority: int, hex_text: str) -> Any:
    with ui.element("div").classes("payload-strip font-mono"):
        with ui.row().classes("items-center gap-2"):
            ui.label("CAN Payload:")
            label = ui.label(hex_text).classes("signal-val").style(
                "font-weight:700;color:#1F2A37;letter-spacing:0.04em;"
            )
        ui.label(f"DLC: 8 Bytes · Priority: {priority}").style("color:#64748B;")
    return label


def _bind(sig: SignalState, attr: str) -> Callable[[float], None]:
    def _set(v: float) -> None:
        setattr(sig, attr, float(v))
        sig.notify()

    return _set


def follow_meter(
    sig: SignalState,
    attr: str,
    sync: Callable[[float], None],
    payload_label: Any,
    encode: Callable[[SignalState], bytes],
    min_step: float,
) -> None:
    """Mirror a value the session's meter thread advances off the UI thread (1 s poll)."""
    shown = [getattr(sig, attr)]

    def poll() -> None:
        value = getattr(sig, attr)
        if abs(value - shown[0]) >= min_step:
            shown[0] = value
            sync(value)
            payload_label.set_text(payload_hex(encode(sig)))

    ui.timer(1.0, poll)


def engine_off_note(sig: SignalState, label: str, text: str) -> None:
    """Header chip shown while the key is ON with the engine off; the full text on hover."""
    note = ui.label(label).classes("engine-off-chip font-mono").tooltip(text)
    note.set_visibility(not sig.engine_running)
    ui.timer(0.5, lambda: note.set_visibility(not sig.engine_running))


def build_ignition(sig: SignalState) -> None:
    """Key switch: key ON with the engine off, or engine running."""
    with ui.element("div").classes("pgn-card"):
        with ui.element("div").classes("pgn-header"):
            with ui.element("div").classes("pgn-title-group"):
                ui.label("KEY").classes("badge-acronym font-mono")
                ui.label("Ignition").classes("pgn-name")
            with ui.element("div").classes("ign-switch"):
                btn_on = ui.button("Key ON · engine off", icon="vpn_key", color=None).classes(
                    "ign-btn"
                ).props("flat no-caps")
                btn_run = ui.button("Engine running", icon="play_circle", color=None).classes(
                    "ign-btn"
                ).props("flat no-caps")
        ui.label(
            "Key ON, engine off: the ECU stays on the bus and answers requests (VIN, odometer, "
            "engine hours), but sends 0 rpm and 0 mph and the meters stand still. "
            "Switching sets Engine Speed to idle 650 rpm (engine running) or 0 rpm (key ON); "
            "setting Engine Speed to 0 rpm or to 600 rpm and above switches it back."
        ).style("font-size:11px;color:#5B6775;padding:8px 12px;")

        shown: list[bool | None] = [None]

        def paint() -> None:
            running = sig.engine_running
            if shown[0] is running:
                return
            shown[0] = running
            btn_on.classes(remove="active-on")
            btn_run.classes(remove="active-run")
            if running:
                btn_run.classes(add="active-run")
            else:
                btn_on.classes(add="active-on")

        def choose(running: bool) -> None:
            if running != sig.engine_running:
                sig.set_ignition(running)  # also moves Engine Speed to idle / 0 rpm
            paint()

        btn_on.on_click(lambda: choose(False))
        btn_run.on_click(lambda: choose(True))
        paint()
        ui.timer(0.5, paint)  # follows changes from another browser tab or the CLI


def build_eec1(sig: SignalState, payload_labels: dict) -> None:
    with ui.element("div").classes("pgn-card"):
        details, badges = pgn_header(
            "EEC1",
            "Electronic Engine Controller 1",
            61444,
            0x0CF00400,
            sig.cycle_eec1_ms,
            lambda ms: (setattr(sig, "cycle_eec1_ms", ms), sig.notify()),
            sig.eec1_enabled,
        )
        with details:
            payload_labels["eec1"] = payload_strip(3, payload_hex(encode_eec1(sig)))
        with badges:
            engine_off_note(
                sig, "ENGINE OFF · 0 rpm",
                "Engine off: sending 0 rpm. Set 600 rpm or more, or start the engine, to run.",
            )
        sync_rpm = slider_spn(
            "SPN 190", "Engine Speed", "rpm", sig.spn190_rpm, 0, 3500, 25,
            sig.set_engine_speed,  # 0 rpm / >= 600 rpm also flip the ignition switch
            presets=[("0 rpm", 0), ("Idle 650", 650), ("Cruise 1250", 1250), ("Rated 2100", 2100)],
        )
        shown = [sig.spn190_rpm]

        def follow_rpm() -> None:
            # The ignition switch (or another tab) changes rpm outside this slider.
            if sig.spn190_rpm != shown[0]:
                shown[0] = sig.spn190_rpm
                sync_rpm(sig.spn190_rpm)

        ui.timer(0.3, follow_rpm)


def build_ccvs(sig: SignalState, payload_labels: dict) -> None:
    with ui.element("div").classes("pgn-card"):
        details, badges = pgn_header(
            "CCVS",
            "Cruise Control / Vehicle Speed",
            65265,
            0x18FEF100,
            sig.cycle_ccvs_ms,
            lambda ms: (setattr(sig, "cycle_ccvs_ms", ms), sig.notify()),
            sig.ccvs_enabled,
        )
        with details:
            payload_labels["ccvs"] = payload_strip(6, payload_hex(encode_ccvs(sig)))
        with badges:
            engine_off_note(
                sig, "ENGINE OFF · 0 mph",
                "Engine off: sending 0 mph. This setting is used once the engine runs.",
            )
        slider_spn(
            "SPN 84", "Wheel-Based Vehicle Speed", "mph", sig.spn84_speed_mph, 0, 120, 0.5,
            _bind(sig, "spn84_speed_mph"),
            presets=[("0 mph", 0), ("5 mph", 5), ("35 mph", 35), ("65 mph", 65)],
            decimals=1,
        )


def build_vd(sig: SignalState, payload_labels: dict) -> None:
    with ui.element("div").classes("pgn-card"):
        details, _ = pgn_header(
            "VD",
            "Vehicle Distance (Odometer)",
            65248,
            0x18FEE000,
            sig.cycle_vd_ms,
            lambda ms: (setattr(sig, "cycle_vd_ms", ms), sig.notify()),
            sig.vd_enabled,
        )
        with details:
            payload_labels["vd"] = payload_strip(6, payload_hex(encode_vd(sig)))
        sync_odo = counter_spn(
            "SPN 245", "Total Vehicle Distance", "mi", sig.spn245_total_mi, 999999, 1,
            _bind(sig, "spn245_total_mi"), steps=(10, 100, 1000),
            hint="Adds miles automatically while the ECU is running, based on Wheel-Based Vehicle Speed.",
        )
        follow_meter(sig, "spn245_total_mi", sync_odo, payload_labels["vd"], encode_vd, 0.05)


def build_hours(sig: SignalState, payload_labels: dict) -> None:
    with ui.element("div").classes("pgn-card"):
        details, _ = pgn_header(
            "HOURS",
            "Engine Hours, Revolutions",
            65253,
            0x18FEE500,
            sig.cycle_hours_ms,
            lambda ms: (setattr(sig, "cycle_hours_ms", ms), sig.notify()),
            sig.hours_enabled,
        )
        with details:
            payload_labels["hours"] = payload_strip(6, payload_hex(encode_hours(sig)))
        sync_hours = counter_spn(
            "SPN 247", "Engine Total Hours of Operation", "h", sig.spn247_engine_hours, 99999, 2,
            _bind(sig, "spn247_engine_hours"), steps=(1, 10, 100),
            hint="Counts up automatically while the ECU is running and Engine Speed > 0 rpm.",
        )
        follow_meter(sig, "spn247_engine_hours", sync_hours, payload_labels["hours"], encode_hours, 0.005)


# SAE J1939-81 NAME industry groups
_INDUSTRY_GROUPS = {
    0: "Global",
    1: "On-Highway",
    2: "Agricultural & Forestry",
    3: "Construction",
    4: "Marine",
    5: "Industrial / Process",
}
# Vehicle systems defined for industry group 1 (On-Highway)
_ON_HIGHWAY_VEHICLE_SYSTEMS = {0: "Non-specific", 1: "Tractor", 2: "Trailer"}


def build_ecu_pane(session, refs: dict[str, Any]) -> None:
    """ECU & Vehicle (VIN) tab."""
    identity = session.identity
    sa = f"0x{identity.source_address:02X}"
    sa_role = " (Engine #1)" if identity.source_address == 0x00 else ""
    industry = _INDUSTRY_GROUPS.get(identity.industry_group, "Reserved")
    function = " (Engine)" if identity.function == 0 else ""
    vehicle_system = (
        f" ({_ON_HIGHWAY_VEHICLE_SYSTEMS[identity.vehicle_system]})"
        if identity.industry_group == 1 and identity.vehicle_system in _ON_HIGHWAY_VEHICLE_SYSTEMS
        else ""
    )

    with ui.element("div").classes("card").style(
        "display:flex;flex-direction:column;gap:16px;"
    ):
        with ui.row().classes("w-full items-center justify-between").style(
            "border-bottom:1px solid #CBD5E1;padding-bottom:8px;"
        ):
            with ui.column().classes("gap-0"):
                ui.label(f"ECU & Vehicle Identity (Node {sa})").style(
                    "font-size:14px;font-weight:700;text-transform:uppercase;"
                )
                ui.label(
                    "Single ECU node · SAE J1939-81 Network Management"
                ).classes("font-mono").style("font-size:11px;color:#5B6775;")
            claim_chip = ui.element("span").classes("status-pill stopped font-mono").style(
                "font-size:10px;"
            )
            with claim_chip:
                ui.element("span").classes("status-dot")
                claim_label = ui.label("NODE OFFLINE")
            refs["claim_chip"] = claim_chip
            refs["claim_label"] = claim_label

        with ui.element("div").style(
            "display:grid;grid-template-columns:repeat(auto-fit,minmax(min(300px,100%),1fr));gap:16px;"
        ):
            with ui.column().classes("gap-3 items-stretch min-w-0"):
                with ui.element("div").style(
                    "background:#F8FAFC;border:1px solid #CBD5E1;border-radius:3px;"
                    "padding:16px;text-align:center;"
                ):
                    ui.image("/assets/truck.svg").props("fit=contain no-spinner").style(
                        "width:100%;max-width:280px;height:160px;margin:0 auto;"
                        "mix-blend-mode:multiply;"
                    )
                    ui.label(f"Heavy Duty Truck · Node {sa}").classes(
                        "font-mono"
                    ).style(
                        "margin-top:8px;font-size:11px;font-weight:700;color:#1F2A37;"
                    )

                with ui.element("div").style(
                    "background:#F8FAFC;border:1px solid #CBD5E1;border-radius:3px;padding:12px;"
                ):
                    ui.label("Vehicle Identification Number (VIN)").classes("field-label")
                    with ui.element("div").classes("vin-row"):
                        vin_input = (
                            ui.input(value=identity.vin)
                            .props("dense outlined maxlength=17")
                            .classes("vin-input font-mono")
                        )
                        btn_set_vin = ui.button("Set").classes(
                            "action-btn btn-start font-mono"
                        ).props("unelevated dense")
                        btn_copy = ui.button("Copy").classes(
                            "action-btn btn-restart font-mono"
                        ).props("unelevated dense")
                        btn_generate = ui.button("Generate").classes(
                            "action-btn btn-restart font-mono"
                        ).props("unelevated dense")
                    ui.label(
                        "Broadcast on START, when Set, and on Request "
                        "(PGN 59904) — PGN 65260 via BAM."
                    ).style("font-size:11px;color:#5B6775;margin-top:6px;")
                    refs["vin_input"] = vin_input

                    def on_vin_change(e=None) -> None:
                        raw = vin_input.value if e is None else getattr(e, "value", vin_input.value)
                        try:
                            cleaned = session.set_vin(str(raw or ""))
                            vin_input.value = cleaned
                            ui.notify(f"VIN set to {cleaned}", type="positive")
                            if warning := vin_check_digit_warning(cleaned):
                                ui.notify(warning, type="warning")
                        except ValueError as exc:
                            ui.notify(str(exc), type="negative")
                            vin_input.value = identity.vin

                    def on_copy() -> None:
                        text = str(vin_input.value or identity.vin)
                        try:
                            ui.clipboard.write(text)
                            ui.notify(f"VIN copied: {text}", type="info")
                        except Exception:
                            ui.notify(f"VIN: {text}", type="info")

                    def on_generate() -> None:
                        vin_input.value = generate_vin(identity.vin)
                        ui.notify("New VIN generated — press Set to apply", type="info")

                    btn_set_vin.on_click(lambda: on_vin_change())
                    btn_copy.on_click(on_copy)
                    btn_generate.on_click(on_generate)

            with ui.column().classes("gap-3 items-stretch min-w-0"):
                with ui.element("div").style(
                    "background:#F8FAFC;border:1px solid #CBD5E1;border-radius:3px;padding:12px;"
                ):
                    ui.label("J1939-81 Network Address Parameters").style(
                        "font-weight:700;font-size:11px;text-transform:uppercase;"
                        "color:#1F2A37;margin-bottom:8px;"
                    )
                    with ui.element("div").classes("font-mono").style(
                        "display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:11px;"
                    ):
                        for key, label, value in (
                            ("sa", "Source Address (SA):", f"{sa}{sa_role}"),
                            ("industry", "Industry Group:", f"{identity.industry_group} ({industry})"),
                            ("vehicle_system", "Vehicle System:", f"{identity.vehicle_system}{vehicle_system}"),
                            ("function", "Function:", f"{identity.function}{function}"),
                            ("manufacturer", "Manufacturer Code:", str(identity.manufacturer_code)),
                            ("identity", "Identity Number:", str(identity.identity_number)),
                            ("bitrate", "Bitrate:", f"{session.bitrate // 1000} kbit/s"),
                        ):
                            with ui.element("div").style(
                                "background:#FFF;padding:6px;border:1px solid #CBD5E1;"
                                "border-radius:3px;"
                            ):
                                ui.label(label).style(
                                    "color:#5B6775;font-size:10px;display:block;"
                                )
                                refs[f"ecu_{key}"] = ui.label(value).style("font-weight:700;")
                    with ui.element("div").classes("font-mono").style(
                        "margin-top:8px;background:#FFF;padding:8px;"
                        "border:1px solid #CBD5E1;border-radius:3px;"
                    ):
                        ui.label("64-Bit Device NAME:").style(
                            "color:#5B6775;font-size:10px;display:block;"
                        )
                        ui.label(identity.name_hex).style(
                            "font-weight:700;color:#1F6FEB;"
                        )


_REQUEST_COLUMNS = [
    {"name": "time", "label": "Time", "field": "time", "align": "left"},
    {"name": "src", "label": "From", "field": "src", "align": "left"},
    {"name": "dest", "label": "To", "field": "dest", "align": "left"},
    {"name": "pgn", "label": "PGN", "field": "pgn", "align": "left"},
    {"name": "result", "label": "Result", "field": "result", "align": "left"},
]


def _request_rows(session) -> list[dict[str, Any]]:
    rows = []
    for i, ev in enumerate(reversed(session.recent_requests())):  # newest first
        name = f" {ev.pgn_name}" if ev.pgn_name else ""
        rows.append({
            "id": i,
            "time": time.strftime("%H:%M:%S", time.localtime(ev.at)) + f".{int(ev.at * 1000) % 1000:03d}",
            "src": f"0x{ev.src:02X}",
            "dest": "Global" if ev.dest == 0xFF else f"0x{ev.dest:02X}",
            "pgn": f"{ev.pgn}{name}",
            "result": ev.result or "pending",
        })
    return rows


_TRAFFIC_ID = "j1939-traffic"
_TRAFFIC_COLUMNS = ("Time", "Dir", "CAN ID", "PGN", "SA", "DA", "Type", "Data", "Decoded")
_FILTER_HELP = (
    "Words separated by spaces must all match; -word hides rows that contain it. "
    "Field filters: pgn:65260  sa:F9  da:00  id:18EA  type:request  dir:rx. "
    "Example: sa:f9 -tp.dt"
)

# Rows are drawn in the browser: the server only sends the new frames each tick. Cyclic
# broadcasts and everything else are capped separately at TRAFFIC_ROWS rows each (oldest
# dropped first), so the page stays fast and a 20 ms EEC1 cannot push a request out of view.
# Filtering runs here too, over the rows already drawn and each new one.
_TRAFFIC_JS = """
<script>
window.j1939Traffic = (() => {
  const MAX = %d;
  const FIELD = {dir: 1, id: 2, pgn: 3, sa: 4, da: 5, type: 6};
  const views = {};
  const el = (id) => document.getElementById(id);
  const atBottom = (w) => w.scrollHeight - w.scrollTop - w.clientHeight < 24;
  const hint = (id, show) => { const h = el(id + '-new'); if (h) h.style.display = show ? '' : 'none'; };
  const store = (k, v) => { try { localStorage.setItem(k, v); } catch (e) {} };
  const load = (k) => { try { return localStorage.getItem(k); } catch (e) { return null; } };
  function parse(q) {
    return q.trim().toLowerCase().split(/\\s+/).filter(Boolean).map((t) => {
      const neg = t.length > 1 && t[0] === '-';
      if (neg) t = t.slice(1);
      const m = t.match(/^(dir|id|pgn|sa|da|type):(.*)$/);
      let val = m ? m[2] : t;
      if (m && (m[1] === 'sa' || m[1] === 'da')) val = val.replace(/^0x/, '').padStart(2, '0');
      return {neg, field: m ? m[1] : null, val};
    }).filter((t) => t.val !== '');
  }
  function matches(v, tr) {
    if (v.hideCyc && tr.dataset.cyc === '1') return false;
    for (const t of v.terms) {
      let ok;
      if (!t.field) ok = tr.dataset.hay.includes(t.val);
      else {
        const cell = tr.cells[FIELD[t.field]].textContent.toLowerCase();
        ok = (t.field === 'sa' || t.field === 'da') ? cell === t.val : cell.includes(t.val);
      }
      if (ok === t.neg) return false;
    }
    return true;
  }
  function count(id) {
    const v = views[id], c = el(id + '-count');
    const total = v.events.length + v.cyclic.length;
    const e = el(id + '-empty');
    if (e) e.style.display = total ? 'none' : '';
    if (!c) return;
    const shown = v.body.querySelectorAll('tr:not(.tr-hidden)').length;
    c.textContent = shown === total ? total + ' frames' : shown + ' of ' + total + ' frames';
  }
  function view(id) {
    if (views[id] && views[id].body.isConnected) return views[id];
    const w = el(id);
    if (!w) return null;
    const v = {w, body: w.querySelector('tbody'), events: [], cyclic: [], terms: [], hideCyc: false};
    views[id] = v;
    w.dataset.follow = '1';
    w.addEventListener('scroll', () => {
      if (!w.offsetParent) return;
      w.dataset.follow = atBottom(w) ? '1' : '0';
      if (atBottom(w)) hint(id, false);
    });
    const q = el(id + '-q'), cyc = el(id + '-cyc');
    if (q) q.value = load('j1939.traffic.q') || '';
    if (cyc) cyc.checked = load('j1939.traffic.hideCyc') === '1';
    v.terms = parse(q ? q.value : '');
    v.hideCyc = !!(cyc && cyc.checked);
    return v;
  }
  return {
    push(id, rows) {
      const v = view(id);
      if (!v) return;
      const follow = v.w.offsetParent ? atBottom(v.w) : v.w.dataset.follow !== '0';
      const frag = document.createDocumentFragment();
      for (const r of rows) {
        const tr = document.createElement('tr');
        tr.className = 'tr-' + r[9];
        for (let i = 0; i < 9; i++) {
          const td = document.createElement('td');
          td.textContent = r[i];
          if (i === 8 && r[i]) td.title = r[i];
          tr.appendChild(td);
        }
        tr.dataset.cyc = r[10] ? '1' : '0';
        tr.dataset.hay = r.slice(0, 9).join(' ').toLowerCase();
        if (!matches(v, tr)) tr.classList.add('tr-hidden');
        (r[10] ? v.cyclic : v.events).push(tr);
        frag.appendChild(tr);
      }
      v.body.appendChild(frag);
      for (const q of [v.events, v.cyclic]) while (q.length > MAX) q.shift().remove();
      count(id);
      if (follow) { v.w.scrollTop = v.w.scrollHeight; hint(id, false); } else hint(id, true);
    },
    filter(id) {
      const v = view(id);
      if (!v) return;
      const q = el(id + '-q'), cyc = el(id + '-cyc');
      v.terms = parse(q ? q.value : '');
      v.hideCyc = !!(cyc && cyc.checked);
      store('j1939.traffic.q', q ? q.value : '');
      store('j1939.traffic.hideCyc', v.hideCyc ? '1' : '0');
      for (const tr of v.body.rows) tr.classList.toggle('tr-hidden', !matches(v, tr));
      count(id);
      if (v.w.dataset.follow !== '0') v.w.scrollTop = v.w.scrollHeight;
    },
    clear(id) {
      const v = view(id);
      if (!v) return;
      v.body.replaceChildren();
      v.events = []; v.cyclic = [];
      count(id);
      hint(id, false);
    },
    bottom(id) {
      const v = view(id);
      if (!v) return;
      v.w.dataset.follow = '1';
      v.w.scrollTop = v.w.scrollHeight;
      hint(id, false);
    },
    shown(id) {
      const v = view(id);
      if (v && v.w.dataset.follow !== '0') this.bottom(id);
    },
  };
})();
</script>
""" % TRAFFIC_ROWS


def _traffic_row(e: TrafficEntry) -> list[Any]:
    """[time, dir, CAN ID, PGN, SA, DA, type, data, decoded, css class, cyclic] for one entry."""
    stamp = time.strftime("%H:%M:%S", time.localtime(e.at)) + f".{int(e.at * 1000) % 1000:03d}"
    if e.arb_id is None:  # bus error summary
        return [stamp, "", "", "", "", "", e.kind, "", e.text, "err", 0]
    _prio, pgn, sa, da = split_id(e.arb_id)
    failed = e.direction == "TX!"
    name = pgn_name(pgn)
    meaning = decode(e.arb_id, e.data)
    if e.text:  # the last TP.DT of a transfer carries the whole reassembled message
        meaning = f"{meaning} -> {e.text}" if meaning else e.text
    return [
        stamp,
        "TX" if failed else e.direction,
        f"{e.arb_id:08X}",
        f"{pgn} {name}" if name else str(pgn),
        f"{sa:02X}",
        f"{da:02X}",
        e.kind,
        e.data.hex(" ").upper() + ("  (send failed)" if failed else ""),
        meaning,
        "err" if failed else e.direction.lower(),
        1 if e.cyclic else 0,
    ]


def build_traffic_pane(session) -> Callable[[], None]:
    """Traffic tab: live J1939 frames (TX and RX) from the session trace, decoded and filterable.

    PAUSE, CLEAR and the filter only affect this view; the ECU, the bus and the trace keep
    running. Returns a callback for when the tab is shown (scrolls to the newest frame).
    """
    ui.add_body_html(_TRAFFIC_JS)
    with ui.element("div").classes("card traffic-card"):
        with ui.row().classes("w-full items-center justify-between").style(
            "border-bottom:1px solid #CBD5E1;padding-bottom:8px;"
        ):
            with ui.column().classes("gap-0"):
                ui.label("J1939 Traffic Monitor").style(
                    "font-size:14px;font-weight:700;text-transform:uppercase;"
                )
                ui.label(
                    f"Every frame sent and received, decoded from the bytes on the wire · "
                    f"last {TRAFFIC_ROWS} cyclic + last {TRAFFIC_ROWS} other frames"
                ).classes("font-mono").style("font-size:11px;color:#5B6775;")
            with ui.row().classes("items-center gap-2"):
                status = ui.label("● LIVE").classes("traffic-status live font-mono")
                btn_pause = ui.button("Pause").classes("action-btn btn-restart font-mono").props(
                    "unelevated dense"
                )
                btn_clear = ui.button("Clear").classes("action-btn btn-restart font-mono").props(
                    "unelevated dense"
                )
                btn_export = ui.button("Export").classes("action-btn btn-restart font-mono").props(
                    "unelevated dense"
                ).tooltip(
                    "Save the frames in memory as a candump log (all frames, filter not applied): "
                    "replay with canplayer, open in SavvyCAN or Wireshark"
                )
        head = "".join(f"<th>{c}</th>" for c in _TRAFFIC_COLUMNS)
        tid = _TRAFFIC_ID
        ui.html(
            f'<div class="traffic-filter font-mono">'
            f'<input id="{tid}-q" class="traffic-q" type="search" spellcheck="false" '
            f'placeholder="Filter: 65260   sa:F9   type:request   -tp.dt" title="{_FILTER_HELP}" '
            f"oninput=\"j1939Traffic.filter('{tid}')\">"
            f'<label class="traffic-chk"><input id="{tid}-cyc" type="checkbox" '
            f"onchange=\"j1939Traffic.filter('{tid}')\"> Hide cyclic (EEC1, CCVS, VD, HOURS)</label>"
            f'<span id="{tid}-count" class="traffic-count"></span>'
            f"</div>"
            f'<div class="traffic-box">'
            f'<div id="{tid}" class="traffic-wrap">'
            f'<table class="traffic-table"><thead><tr>{head}</tr></thead><tbody></tbody></table>'
            f'<div id="{tid}-empty" class="traffic-empty">'
            f"No traffic yet. Press START to see the frames on the bus.</div>"
            f"</div>"
            f'<button id="{tid}-new" class="traffic-new font-mono" style="display:none" '
            f"onclick=\"j1939Traffic.bottom('{tid}')\">&darr; New messages</button>"
            f"</div>",
            sanitize=False,
        ).classes("w-full")

    view: dict[str, Any] = {"trace": None, "seq": 0, "paused": False, "paused_seq": 0}

    def push(rows: list[list[Any]]) -> None:
        ui.run_javascript(f"j1939Traffic.push('{_TRAFFIC_ID}', {json.dumps(rows)})")

    def refresh() -> None:
        if view["paused"]:
            return
        trace = session.trace
        if trace is None:
            return
        if trace is not view["trace"]:  # a new START: its frames are numbered from 1 again
            view["trace"], view["seq"] = trace, 0
        last, entries = trace.traffic_since(view["seq"])
        view["seq"] = last
        if entries:
            push([_traffic_row(e) for e in entries[-2 * TRAFFIC_ROWS:]])

    def on_pause() -> None:
        view["paused"] = not view["paused"]
        trace = session.trace
        if view["paused"]:
            view["paused_seq"] = trace.traffic_seq() if trace is not None else 0
            status.set_text("● PAUSED")
            status.classes(remove="live", add="paused")
            btn_pause.set_text("Resume")
            return
        status.set_text("● LIVE")
        status.classes(remove="paused", add="live")
        btn_pause.set_text("Pause")
        # Resume from the newest frame; say how many went by unseen instead of dumping them.
        if trace is not None:
            now_seq = trace.traffic_seq()
            same_run = trace is view["trace"]
            missed = now_seq - view["paused_seq"] if same_run else now_seq
            view["trace"], view["seq"] = trace, now_seq
            if missed > 0:
                stamp = time.strftime("%H:%M:%S")
                push([[stamp, "", "", "", "", "", "PAUSED", "",
                       f"{missed} frames not shown while paused", "gap", 0]])

    def on_export() -> None:
        trace = session.trace
        if trace is None:
            ui.notify("No traffic yet: press START first.", type="warning")
            return
        path = trace_dir() / time.strftime("traffic-%Y%m%d-%H%M%S.log")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            n = trace.export_candump(path)
        except OSError as exc:
            ui.notify(f"Export failed: {exc}", type="negative")
            return
        if n == 0:
            ui.notify("No frames to export.", type="warning")
            return
        ui.download(path)
        ui.notify(f"Exported {n} frames (candump log): {path}", type="positive")

    btn_pause.on_click(on_pause)
    btn_clear.on_click(lambda: ui.run_javascript(f"j1939Traffic.clear('{_TRAFFIC_ID}')"))
    btn_export.on_click(on_export)
    ui.timer(0.25, refresh)
    return lambda: ui.run_javascript(f"j1939Traffic.shown('{_TRAFFIC_ID}')")


def build_logs_pane(session, refs: dict[str, Any]) -> None:
    """Logs panel (always visible): incoming requests and the J1939 trace, for ELD bench debugging."""
    with ui.element("div").classes("card logs-panel"):
        with ui.column().classes("gap-0").style(
            "border-bottom:1px solid #CBD5E1;padding-bottom:8px;"
        ):
            with ui.row().classes("w-full items-center gap-2"):
                ui.label("Logs").style(
                    "font-size:14px;font-weight:700;text-transform:uppercase;"
                )
                refs["logs_pill"] = ui.label("0 Requests").classes("tab-pill font-mono").style(
                    "margin-left:0;"
                )
                ui.space()
                paused = ui.label("PAUSED").classes("logs-paused font-mono")
                live = ui.switch("Live", value=True).props("dense color=positive").classes(
                    "logs-live font-mono"
                )
            ui.label(
                "Requests from other nodes and a decoded J1939 trace of each run"
            ).classes("font-mono").style("font-size:11px;color:#5B6775;")
        # Pausing only freezes this panel; the trace file keeps recording, and the panel
        # catches up with what it missed when monitoring is switched back on.
        monitor = {"on": True}

        def on_live(e) -> None:
            monitor["on"] = bool(e.value)
            paused.set_visibility(not monitor["on"])

        live.on_value_change(on_live)
        paused.set_visibility(False)
        build_request_log(session, monitor)
        build_trace_view(session, monitor)


def build_request_log(session, monitor: dict[str, bool]) -> None:
    """Requests (PGN 59904) from other nodes, e.g. an ELD asking for the VIN."""
    with ui.element("div").style(
        "background:#F8FAFC;border:1px solid #CBD5E1;border-radius:3px;padding:12px;"
    ):
        with ui.row().classes("w-full items-center justify-between"):
            with ui.column().classes("gap-0"):
                ui.label("Incoming Requests (PGN 59904)").style(
                    "font-weight:700;font-size:11px;text-transform:uppercase;color:#1F2A37;"
                )
                ui.label(
                    "Last 50 requests from other nodes and how this ECU answered, newest first."
                ).style("font-size:11px;color:#5B6775;")
            btn_clear = ui.button("Clear").classes(
                "action-btn btn-restart font-mono"
            ).props("unelevated dense")
        table = ui.table(columns=_REQUEST_COLUMNS, rows=[], row_key="id").props(
            "dense flat bordered hide-bottom"
        ).classes("w-full font-mono").style("font-size:11px;margin-top:8px;")
        empty = ui.label("No requests received yet.").classes("font-mono").style(
            "font-size:11px;color:#5B6775;margin-top:6px;"
        )

    shown: list[dict[str, Any]] = []

    def refresh(force: bool = False) -> None:
        if not (monitor["on"] or force):
            return
        rows = _request_rows(session)
        if rows == shown:
            return
        shown[:] = rows
        table.rows = rows
        table.update()
        table.set_visibility(bool(rows))
        empty.set_visibility(not rows)

    def on_clear() -> None:
        session.clear_requests()
        refresh(force=True)

    btn_clear.on_click(on_clear)
    table.set_visibility(False)
    ui.timer(0.5, refresh)


def build_trace_view(session, monitor: dict[str, bool]) -> None:
    """Live J1939 trace (also written to a file per START) for debugging an ELD on the bench."""
    with ui.element("div").style(
        "background:#F8FAFC;border:1px solid #CBD5E1;border-radius:3px;padding:12px;"
    ):
        with ui.row().classes("w-full items-center justify-between"):
            with ui.column().classes("gap-0"):
                ui.label("J1939 Trace").style(
                    "font-weight:700;font-size:11px;text-transform:uppercase;color:#1F2A37;"
                )
                path_label = ui.label("Starts with START: requests, transport frames (BAM / RTS / CTS / "
                                      "EOMA / Abort), replies, send and bus errors.").classes(
                    "font-mono"
                ).style("font-size:11px;color:#5B6775;word-break:break-all;")
            btn_download = ui.button("Download").classes(
                "action-btn btn-restart font-mono"
            ).props("unelevated dense")
        log = ui.log(max_lines=500).classes("trace-log w-full font-mono").style(
            "font-size:11px;margin-top:8px;background:#FFF;white-space:pre;"
        )

    view = {"trace": None, "count": 0}

    def refresh() -> None:
        if not monitor["on"]:
            return
        trace = session.trace
        if trace is None:
            return
        if trace is not view["trace"]:
            view["trace"], view["count"] = trace, 0
            log.clear()
            path_label.set_text(f"File: {trace.path}" if trace.path else "File: not available (in-app only)")
        count, lines = trace.recent()
        new = count - view["count"]
        if new <= 0:
            return
        for line in lines[-min(new, len(lines)):]:
            log.push(line)
        view["count"] = count

    def on_download() -> None:
        trace = session.trace
        if trace is None or trace.path is None or not trace.path.exists():
            ui.notify("No trace file yet: press START first.", type="warning")
            return
        ui.download(trace.path)

    btn_download.on_click(on_download)
    ui.timer(0.5, refresh)


def build_diagnostics_pane(session, refs: dict[str, Any]) -> None:
    """Diagnostics tab — 2 DTCs on DM1."""
    diag = session.diagnostics

    with ui.element("div").classes("card").style(
        "display:flex;flex-direction:column;gap:14px;"
    ):
        with ui.row().classes("w-full items-center justify-between").style(
            "border-bottom:1px solid #CBD5E1;padding-bottom:8px;"
        ):
            with ui.column().classes("gap-0"):
                ui.label("Diagnostics & Active Fault Codes (DM1)").style(
                    "font-size:14px;font-weight:700;text-transform:uppercase;"
                )
                ui.label(
                    "SAE J1939-73 Diagnostic Trouble Code (DTC) Fault Injection & Lamp Status"
                ).classes("font-mono").style("font-size:11px;color:#5B6775;")
            with ui.row().classes("gap-2"):
                btn_clear = ui.button("Clear All").classes(
                    "action-btn btn-restart font-mono"
                ).props("unelevated dense")
                btn_inject = ui.button("Inject Both").classes(
                    "action-btn btn-restart font-mono"
                ).props("unelevated dense")

        dm1_alert = ui.element("div").classes("font-mono").style(
            "display:none;background:#FFFBEB;border:1px solid #FDE68A;border-radius:3px;"
            "padding:10px;font-size:11px;color:#92400E;"
        )
        with dm1_alert:
            ui.label("PGN 65226 (DM1) Active Diagnostic Message Broadcast").style(
                "font-weight:700;"
            )
            ui.label(
                "CAN ID: 0x18FECA00 · Priority: 6 · Rate: 1000 ms. "
                "Telematics dashboards display MIL indicator."
            )
        refs["dm1_alert"] = dm1_alert

        with ui.element("div").classes("dtc-grid"):
            card1 = ui.element("div").classes("dtc-card")
            with card1:
                with ui.row().classes("w-full items-center justify-between").style(
                    "margin-bottom:8px;"
                ):
                    ui.label("SPN 110 / FMI 3").classes("badge-subtle font-mono").style(
                        "background:#FFFBEB;color:#B45309;border-color:#FDE68A;"
                    )
                    badge1 = ui.label("INACTIVE").classes("tab-pill font-mono")
                ui.label("Engine Coolant Temp Voltage High").style(
                    "font-weight:700;font-size:13px;color:#1F2A37;"
                )
                ui.label(
                    "Voltage Above Normal, Or Shorted To High Source. Amber Warning Lamp."
                ).style("font-size:11px;color:#5B6775;margin-top:4px;")
                with ui.row().classes("w-full items-center justify-between").style(
                    "border-top:1px solid #CBD5E1;padding-top:8px;"
                ):
                    ui.label("Lamp: Amber Warning").classes("font-mono").style(
                        "font-size:11px;color:#5B6775;"
                    )
                    btn1 = ui.button("Inject Fault").classes(
                        "action-btn btn-restart font-mono"
                    ).props("unelevated dense")

            card2 = ui.element("div").classes("dtc-card")
            with card2:
                with ui.row().classes("w-full items-center justify-between").style(
                    "margin-bottom:8px;"
                ):
                    ui.label("SPN 190 / FMI 0").classes("badge-subtle font-mono").style(
                        "background:#FEF2F2;color:#991B1B;border-color:#FCA5A5;"
                    )
                    badge2 = ui.label("INACTIVE").classes("tab-pill font-mono")
                ui.label("Engine Crankshaft Overspeed").style(
                    "font-weight:700;font-size:13px;color:#1F2A37;"
                )
                ui.label(
                    "Data Valid But Above Normal Operational Range - Most Severe Level. "
                    "Red Stop Lamp."
                ).style("font-size:11px;color:#5B6775;margin-top:4px;")
                with ui.row().classes("w-full items-center justify-between").style(
                    "border-top:1px solid #CBD5E1;padding-top:8px;"
                ):
                    ui.label("Lamp: Red Stop Lamp").classes("font-mono").style(
                        "font-size:11px;color:#5B6775;"
                    )
                    btn2 = ui.button("Inject Fault").classes(
                        "action-btn btn-restart font-mono"
                    ).props("unelevated dense")

        refs.update(
            {
                "dtc_card1": card1,
                "dtc_card2": card2,
                "dtc_badge1": badge1,
                "dtc_badge2": badge2,
                "dtc_btn1": btn1,
                "dtc_btn2": btn2,
            }
        )

        def refresh_dtc_ui() -> None:
            c = diag.active_count
            dm1_alert.style(
                "display:block;background:#FFFBEB;border:1px solid #FDE68A;"
                "border-radius:3px;padding:10px;font-size:11px;color:#92400E;"
                if c > 0
                else "display:none;"
            )
            if diag.dtc_spn110_fmi3:
                card1.classes(remove="fault-red", add="fault-amber")
                badge1.set_text("FAULT INJECTED")
                btn1.set_text("Clear Fault")
            else:
                card1.classes(remove="fault-amber fault-red")
                badge1.set_text("INACTIVE")
                btn1.set_text("Inject Fault")
            if diag.dtc_spn190_fmi0:
                card2.classes(remove="fault-amber", add="fault-red")
                badge2.set_text("FAULT INJECTED")
                btn2.set_text("Clear Fault")
            else:
                card2.classes(remove="fault-amber fault-red")
                badge2.set_text("INACTIVE")
                btn2.set_text("Inject Fault")
            pill = refs.get("diag_tab_pill")
            if pill is not None:
                if c > 0:
                    pill.set_text(f"{c} Active")
                    pill.classes(add="warn")
                else:
                    pill.set_text("2 Supported")
                    pill.classes(remove="warn")
            foot = refs.get("foot_dtc")
            if foot is not None:
                if c > 0:
                    foot.set_text(f"Active Faults: {c} DTCs")
                    foot.style("color:#B45309")
                else:
                    foot.set_text("Active Faults: 0 DTCs")
                    foot.style("color:#1F9D55")

        refs["refresh_dtc_ui"] = refresh_dtc_ui

        btn1.on_click(lambda: (session.set_dtc1(not diag.dtc_spn110_fmi3), refresh_dtc_ui()))
        btn2.on_click(lambda: (session.set_dtc2(not diag.dtc_spn190_fmi0), refresh_dtc_ui()))
        btn_clear.on_click(lambda: (session.clear_all_dtcs(), refresh_dtc_ui()))
        btn_inject.on_click(lambda: (session.inject_both_dtcs(), refresh_dtc_ui()))
        refresh_dtc_ui()
