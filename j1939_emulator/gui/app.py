"""NiceGUI web application: bus control, signals, ECU/VIN and diagnostics tabs."""

from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Any

from nicegui import app, ui

from j1939_emulator.bus.detect import (
    DetectedChannel,
    EmulationMode,
    detect_hardware,
    match_channel,
    resolve_channel,
)
from j1939_emulator.bus.session import BusHealth, EmulatorSession
from j1939_emulator.config import load_config
from j1939_emulator.meters_store import restore_meters
from j1939_emulator.gui.styles import APP_CSS, FONTS_HTML
from j1939_emulator.gui.widgets import (
    build_ccvs,
    build_diagnostics_pane,
    build_ecu_pane,
    build_faults_pane,
    build_logs_pane,
    build_scenarios_pane,
    build_traffic_pane,
    build_eec1,
    build_ignition,
    build_hours,
    build_hrvd,
    build_tco1,
    build_vd,
)
from j1939_emulator.pgn import SignalState, all_payloads
from j1939_emulator.diagnostics import DiagnosticState
from j1939_emulator.faults import active_faults
from j1939_emulator.scenario import RunState, ScenarioRunner, format_time
from j1939_emulator.ecu_identity import EcuIdentity

BITRATE_OPTIONS = {
    "125 kbit/s": 125_000,
    "250 kbit/s (Traditional / Common)": 250_000,
    "500 kbit/s (J1939 / Modern)": 500_000,
    "1000 kbit/s (FD)": 1_000_000,
}

# Status pill text and the one-time hint shown when the bus goes unhealthy.
BUS_HEALTH_TEXT = {
    BusHealth.NO_ACK: (
        "No ACK",
        "No node acknowledges our frames. Check CAN-H/CAN-L wiring and 120 Ω termination "
        "(~60 Ω between H and L). A listen-only ELD never ACKs — add a second node in normal mode.",
    ),
    BusHealth.TX_FAILING: (
        "TX failing",
        "The adapter is not sending frames (TX timeouts). Check the adapter, cable and bitrate.",
    ),
    BusHealth.BUS_ERRORS: (
        "Bus error",
        "Error frames on the bus. Check that every node uses the same bitrate and the wiring/termination.",
    ),
}
# Health states shown red (frames are not getting out); the rest are amber warnings.
BUS_HEALTH_ERRORS = {BusHealth.TX_FAILING, BusHealth.BUS_ERRORS}

MODE_OPTIONS = {
    "Real Hardware Emulation": EmulationMode.REAL,
    "Virtual Emulation": EmulationMode.VIRTUAL,
}

class GuiState:
    def __init__(self, session: EmulatorSession) -> None:
        self.session = session
        # One runner for the app: a scenario keeps playing when the browser tab is reloaded.
        self.runner = ScenarioRunner(session)
        self.mode = EmulationMode.VIRTUAL
        self.channels: list[DetectedChannel] = []
        self.channel_uid: str | None = None
        self.bitrate = 500_000
        self.payload_labels: dict[str, Any] = {}
        self.ui_refs: dict[str, Any] = {}
        self.host = "127.0.0.1"
        self.port = 8080
        self.config_path: str | None = None
        self.open_browser = True
        # CLI overrides (--mode/--channel/--bitrate), carried over on Apply Port relaunch.
        self.cli_overrides: dict[str, Any] = {}
        # Channel named in the config / --channel. While set, never silently fall back to
        # another adapter (e.g. a COM port) when it is missing; cleared by a manual choice.
        self.pinned_channel: str | None = None
        self._relaunch: dict[str, Any] | None = None


def run_gui(
    config_path: str | None = None,
    host: str = "127.0.0.1",
    port: int = 8080,
    open_browser: bool = True,
    mode_override: str | None = None,
    channel_override: str | None = None,
    bitrate_override: int | None = None,
) -> None:
    signals = SignalState()
    identity = EcuIdentity()
    diagnostics = DiagnosticState()
    bitrate = 500_000
    mode = EmulationMode.VIRTUAL
    preferred_channel: str | None = None
    persist_meters = True

    if config_path:
        cfg = load_config(config_path)
        signals = cfg.signals
        identity = cfg.identity
        diagnostics = cfg.diagnostics
        bitrate = cfg.bus.bitrate
        mode = cfg.bus.mode
        preferred_channel = cfg.bus.channel
        persist_meters = cfg.persist_meters

    if persist_meters:
        restore_meters(signals, identity.vin)

    if mode_override:
        mode = EmulationMode(mode_override)
    if channel_override:
        preferred_channel = channel_override
    if bitrate_override:
        bitrate = int(bitrate_override)

    session = EmulatorSession(
        signals=signals,
        identity=identity,
        diagnostics=diagnostics,
        bitrate=bitrate,
        mode=mode,
        persist_meters=persist_meters,
    )
    state = GuiState(session)
    state.mode = mode
    state.bitrate = bitrate
    state.host = host
    state.port = int(port)
    state.config_path = config_path
    state.open_browser = open_browser
    state.cli_overrides = {
        "mode": mode_override,
        "channel": channel_override,
        "bitrate": bitrate_override,
    }

    @app.on_startup
    def _startup() -> None:
        state.channels = detect_hardware(mode=state.mode, timeout=6.0)
        state.pinned_channel = preferred_channel
        if preferred_channel:
            ch = match_channel(state.channels, preferred_channel)
            state.channel_uid = ch.uid if ch is not None else None
        elif state.channels:
            state.channel_uid = state.channels[0].uid
        if state.open_browser:
            url = f"http://{state.host}:{state.port}/"
            try:
                webbrowser.open(url)
            except Exception:
                pass

    @app.on_shutdown
    def _shutdown() -> None:
        state.runner.stop()
        session.stop()

    app.add_static_files("/assets", str(Path(__file__).parent / "assets"))

    @ui.page("/")
    def index_page() -> None:
        ui.add_head_html(FONTS_HTML)
        ui.add_css(APP_CSS)
        _build_page(state)

    ui.run(
        host=host,
        port=port,
        title="SAE J1939 Vehicle Emulator",
        favicon=Path(__file__).parent / "assets" / "brand-icon.svg",
        reload=False,
        show=False,
    )

    if state._relaunch:
        _relaunch_gui(state._relaunch)


def _relaunch_gui(opts: dict[str, Any]) -> None:
    """Restart the GUI process on a new host/port after Apply Port."""
    cmd = [
        sys.executable,
        "-m",
        "j1939_emulator",
        "--gui",
        "--host",
        str(opts["host"]),
        "--port",
        str(opts["port"]),
    ]
    if opts.get("config_path"):
        cmd.extend(["--config", str(opts["config_path"])])
    if not opts.get("open_browser", True):
        cmd.append("--no-browser")
    for flag in ("mode", "channel", "bitrate"):
        if opts.get(flag):
            cmd.extend([f"--{flag}", str(opts[flag])])
    kwargs: dict[str, Any] = {"cwd": os.getcwd()}
    if sys.platform == "win32":
        # Keep a visible console for the restarted server.
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    subprocess.Popen(cmd, **kwargs)


def _selected_channel(state: GuiState) -> DetectedChannel | None:
    for ch in state.channels:
        if ch.uid == state.channel_uid:
            return ch
    return None


def _fmt_uptime(seconds: float) -> str:
    s = int(max(0, seconds))
    return f"{s // 60:02d}:{s % 60:02d}"


def _bitrate_label(bitrate: int) -> str:
    for label, value in BITRATE_OPTIONS.items():
        if value == bitrate:
            return label
    return f"{bitrate} bit/s"


def _build_page(state: GuiState) -> None:
    session = state.session
    sig = session.signals

    with ui.element("div").classes("j1939-root"):
        with ui.element("header").classes("topbar"):
            with ui.element("div").classes("brand-section"):
                ui.image("/assets/brand-icon.svg").classes("brand-icon")
                ui.label("SAE J1939 Vehicle Emulator").classes("brand-title")
            with ui.element("div").classes("topbar-controls"):
                port_badge = ui.label(f"{state.host}:{state.port} ✓").classes(
                    "listen-badge font-mono"
                ).tooltip("The web UI listens here")
                btn_settings = (
                    ui.button(icon="settings", color=None)
                    .classes("icon-btn")
                    .props("flat round dense")
                    .tooltip("Settings: web UI host and port")
                )
                btn_quit = (
                    ui.button("Quit", icon="power_settings_new", color=None)
                    .classes("action-btn btn-ghost")
                    .props("flat dense")
                )

        # Web UI host / port: rarely changed, so it lives in a dialog behind the gear.
        with ui.dialog() as settings_dialog, ui.card().classes("settings-card"):
            ui.label("Settings").classes("pane-title")
            ui.label(
                "Address of this web UI. Apply restarts the UI on the new address."
            ).classes("pane-sub")
            with ui.element("div").classes("settings-fields"):
                with ui.column().classes("gap-0"):
                    ui.label("Host").classes("field-label")
                    host_input = (
                        ui.input(value=state.host)
                        .props("dense outlined")
                        .classes("host-input font-mono")
                    )
                with ui.column().classes("gap-0"):
                    ui.label("Port").classes("field-label")
                    port_input = (
                        ui.number(
                            value=state.port, min=1, max=65535, step=1, format="%.0f"
                        )
                        .props("dense outlined")
                        .classes("port-input font-mono")
                    )
            with ui.element("div").classes("settings-actions"):
                ui.button("Cancel", on_click=settings_dialog.close, color=None).classes(
                    "action-btn btn-restart"
                ).props("flat dense")
                btn_apply_port = ui.button("Apply", color=None).classes(
                    "action-btn btn-primary"
                ).props("flat dense")

        with ui.element("main").classes("j1939-main"):
            with ui.element("section").classes("card bus-bar"):
                with ui.element("div").classes("bus-controls-group"):
                    ui.label("Bus Config").classes("section-caption bus-caption")
                    with ui.column().classes("bus-field gap-0"):
                        ui.label("Emulation Mode").classes("field-label")
                        mode_select = ui.select(
                            options=list(MODE_OPTIONS.keys()),
                            value=next(k for k, v in MODE_OPTIONS.items() if v == state.mode),
                        ).props("dense outlined options-dense").classes("bus-select")

                    with ui.column().classes("bus-field bus-field-wide gap-0"):
                        ui.label("Interface / Channel").classes("field-label")
                        channel_select = ui.select(options={}, value=None).props(
                            "dense outlined options-dense"
                        ).classes("bus-select")

                    with ui.column().classes("bus-field gap-0"):
                        ui.label("Bitrate").classes("field-label")
                        bitrate_select = ui.select(
                            options=list(BITRATE_OPTIONS.keys()),
                            value=_bitrate_label(state.bitrate),
                        ).props("dense outlined options-dense").classes("bus-select")

                    refresh_btn = ui.button("Refresh").props("flat dense")

                with ui.element("div").classes("run-panel"):
                    with ui.element("div").classes("run-controls"):
                        # The one ECU state indicator: a badge, not a button.
                        top_pill = ui.element("span").classes("status-pill ecu-state stopped")
                        with top_pill:
                            ui.element("span").classes("status-dot")
                            top_status = ui.label("Stopped")
                        with ui.element("div").classes("btn-group"):
                            btn_start = ui.button("Start", icon="play_arrow", color=None).classes(
                                "action-btn btn-start"
                            ).props("flat dense")
                            btn_stop = ui.button("Stop", icon="stop", color=None).classes(
                                "action-btn btn-stop"
                            ).props("flat dense")
                            btn_reset = ui.button("Reset", icon="restart_alt", color=None).classes(
                                "action-btn btn-restart"
                            ).props("flat dense")
                    with ui.element("div").classes("run-stats"):
                        ui.label("Uptime")
                        stat_uptime = ui.label("00:00").classes("stat-value font-mono")
                        ui.label("TX")
                        stat_tx = ui.label("0").classes("stat-value font-mono")
                        ui.label("Load")
                        with ui.element("div").classes("load-bar"):
                            load_fill = ui.element("div").classes("load-fill")
                        stat_load = ui.label("0.0%").classes("stat-value font-mono")

            # Tabs on the left; the Logs panel stays visible on the right whatever tab is open.
            with ui.element("div").classes("workspace"):
                with ui.element("div").classes("work-main"):
                    with ui.element("nav").classes("tab-bar"):
                        tab_signals = ui.button().classes("tab-btn active").props("flat dense")
                        with tab_signals:
                            ui.label("Signals (PGNs & SPNs)")
                        tab_ecu = ui.button().classes("tab-btn").props("flat dense")
                        with tab_ecu:
                            ui.label("ECU & Vehicle (VIN)")
                            ui.label(f"Node 0x{session.identity.source_address:02X}").classes("tab-pill")
                        tab_diag = ui.button().classes("tab-btn").props("flat dense")
                        with tab_diag:
                            ui.label("Diagnostics (DTC)")
                            diag_tab_pill = ui.label("").classes("tab-pill warn")
                            diag_tab_pill.set_visibility(False)
                            state.ui_refs["diag_tab_pill"] = diag_tab_pill
                        tab_traffic = ui.button().classes("tab-btn").props("flat dense")
                        with tab_traffic:
                            ui.label("Traffic")
                        tab_faults = ui.button().classes("tab-btn").props("flat dense")
                        with tab_faults:
                            ui.label("Faults")
                            faults_tab_pill = ui.label("None").classes("tab-pill")
                        tab_scen = ui.button().classes("tab-btn").props("flat dense")
                        with tab_scen:
                            ui.label("Scenarios")
                            scen_tab_pill = ui.label("").classes("tab-pill")

                    pane_signals = ui.element("section").classes("signals-pane ecu-stopped")
                    with pane_signals:
                        with ui.row().classes("w-full items-center justify-between").style(
                            "margin-bottom:12px;"
                        ):
                            ui.label(
                                "SAE J1939-71 Application Layer · Real-Time 4 PGN CAN Broadcast"
                            ).classes("pane-sub")

                        scen_banner = ui.element("div").classes("scenario-banner")
                        with scen_banner:
                            ui.icon("play_circle").style("font-size:16px;")
                            scen_banner_text = ui.label()
                        scen_banner.set_visibility(False)

                        stopped_banner = ui.element("div").classes("stopped-banner")
                        with stopped_banner:
                            ui.icon("pause_circle_outline")
                            ui.label(
                                "ECU stopped — values are not broadcast. You can still edit them."
                            ).classes("stopped-banner-text")
                            ui.button(
                                "Start", icon="play_arrow", on_click=lambda: do_start(), color=None
                            ).classes("action-btn btn-start").props("flat dense")

                        state.payload_labels.clear()
                        sig.clear_listeners()

                        build_ignition(sig)
                        build_eec1(session, state.payload_labels)
                        build_ccvs(session, state.payload_labels)
                        build_tco1(session, state.payload_labels)
                        build_vd(session, state.payload_labels)
                        build_hrvd(session, state.payload_labels)
                        build_hours(session, state.payload_labels)

                    pane_ecu = ui.element("section")
                    with pane_ecu:
                        build_ecu_pane(session, state.ui_refs)
                    pane_ecu.set_visibility(False)

                    pane_diag = ui.element("section")
                    with pane_diag:
                        build_diagnostics_pane(session, state.ui_refs)
                    pane_diag.set_visibility(False)

                    pane_traffic = ui.element("section")
                    with pane_traffic:
                        on_traffic_shown = build_traffic_pane(session)
                    pane_traffic.set_visibility(False)

                    pane_faults = ui.element("section")
                    with pane_faults:
                        build_faults_pane(session, state.ui_refs)
                    pane_faults.set_visibility(False)

                    pane_scen = ui.element("section")
                    with pane_scen:
                        build_scenarios_pane(session, state.runner, state.ui_refs)
                    pane_scen.set_visibility(False)

                with ui.element("aside").classes("work-logs"):
                    build_logs_pane(session, state.ui_refs)
                    logs_tab_pill = state.ui_refs["logs_pill"]

        with ui.element("footer").classes("j1939-footer"):
            with ui.element("div").classes("footer-left"):
                foot_sa = ui.label(f"SA: 0x{session.identity.source_address:02X}")
                foot_bitrate = ui.label(f"{state.bitrate // 1000} kbit/s")
            with ui.element("div").classes("footer-right"):
                foot_scen = ui.label("").classes("footer-scenario")
                foot_scen.set_visibility(False)
                foot_faults = ui.label("").classes("footer-faults")
                foot_faults.set_visibility(False)
                foot_peers = ui.label("Other nodes: 0")
                foot_tx = ui.label("TX Broadcast: 0 frames")
                foot_dtc = ui.label("Active Faults: 0 DTCs").classes("footer-dtc")
                state.ui_refs["foot_dtc"] = foot_dtc

    def refresh_channels(*, prefer: DetectedChannel | None = None) -> DetectedChannel | None:
        prior = prefer
        if prior is None and state.channel_uid:
            prior = _selected_channel(state) or session.channel
        state.channels = detect_hardware(mode=state.mode, timeout=6.0)
        options = {ch.uid: ch.label for ch in state.channels}
        channel_select.options = options
        if state.pinned_channel:
            resolved = match_channel(state.channels, state.pinned_channel)
            if resolved is None:
                ui.notify(
                    f"Configured channel {state.pinned_channel!r} not found. "
                    "Connect the adapter and press Refresh, or pick a channel.",
                    type="warning",
                    timeout=10000,
                )
        else:
            resolved = resolve_channel(
                state.channels, uid=state.channel_uid, previous=prior
            )
        state.channel_uid = resolved.uid if resolved else None
        channel_select.value = state.channel_uid
        paint_channel_hint()
        channel_select.update()
        return resolved

    def paint_channel_hint() -> None:
        """Say why Interface / Channel is empty instead of showing a blank field."""
        if not channel_select.options:
            channel_select.props('display-value="None found — press Refresh"')
        elif channel_select.value is None:
            channel_select.props('display-value="Select an interface…"')
        else:
            channel_select.props(remove="display-value")
        channel_select.classes(
            remove="is-hint", add="is-hint" if channel_select.value is None else ""
        )

    def on_mode_change(e) -> None:
        label = e.value if hasattr(e, "value") else mode_select.value
        new_mode = MODE_OPTIONS.get(label, EmulationMode.VIRTUAL)
        if new_mode is state.mode and state.channels:
            return
        if session.running:
            session.stop()
            update_chrome()
        state.mode = new_mode
        state.channel_uid = None
        state.pinned_channel = None
        refresh_channels()

    def on_channel_change(e) -> None:
        state.channel_uid = e.value if hasattr(e, "value") else channel_select.value
        paint_channel_hint()
        if state.channel_uid is not None and state.pinned_channel:
            pinned = match_channel(state.channels, state.pinned_channel)
            if pinned is None or pinned.uid != state.channel_uid:
                state.pinned_channel = None  # the user picked a different adapter

    def on_bitrate_change(e) -> None:
        label = e.value if hasattr(e, "value") else bitrate_select.value
        new_br = BITRATE_OPTIONS.get(label, 500_000)
        state.bitrate = new_br
        session.bitrate = new_br
        foot_bitrate.set_text(f"{state.bitrate // 1000} kbit/s")
        if session.running:
            ch = _selected_channel(state) or session.channel
            if ch is None:
                session.stop()
                update_chrome()
                ui.notify("Bitrate updated — channel lost; press Start", type="warning")
                return
            try:
                # Clean reopen at new bitrate (same channel object; refresh only on fail).
                session.stop()
                session.start(ch, bitrate=state.bitrate)
                update_chrome()
                ui.notify(f"Bitrate applied — restarted on {ch.label}", type="info")
            except Exception as exc:
                session.stop()
                update_chrome()
                ch2 = refresh_channels(prefer=ch)
                if ch2 is not None:
                    try:
                        session.start(ch2, bitrate=state.bitrate)
                        update_chrome()
                        ui.notify(f"Bitrate applied on {ch2.label}", type="info")
                        return
                    except Exception as exc2:
                        session.stop()
                        update_chrome()
                        ui.notify(
                            f"Bitrate set; Start failed: {exc2}. Press Refresh then Start.",
                            type="negative",
                        )
                        return
                ui.notify(
                    f"Bitrate set; Start failed: {exc}. Press Refresh then Start.",
                    type="negative",
                )

    def do_start() -> None:
        ch = _selected_channel(state)
        if ch is None:
            ch = refresh_channels()
        if ch is None:
            ui.notify("No channel selected", type="warning")
            return
        try:
            session.start(ch, bitrate=state.bitrate)
            update_chrome()
            ui.notify(f"Started on {ch.label}", type="positive")
            return
        except Exception as first_exc:
            session.stop()
            update_chrome()
            # Rediscover only after a failed open (USB list right after close is fragile).
            ch2 = refresh_channels(prefer=ch)
            if ch2 is None:
                ui.notify(f"Start failed: {first_exc}", type="negative")
                return
            try:
                session.start(ch2, bitrate=state.bitrate)
                update_chrome()
                ui.notify(f"Started on {ch2.label} (after refresh)", type="positive")
            except Exception as exc:
                session.stop()
                update_chrome()
                ui.notify(f"Start failed: {exc}", type="negative")

    def do_stop() -> None:
        session.stop()
        update_chrome()
        # Defer rediscovery so candleLight USB handles can settle.
        ui.timer(0.8, lambda: refresh_channels(prefer=session.channel), once=True)

    def do_reset() -> None:
        ch = _selected_channel(state) or session.channel
        if ch is None:
            ch = refresh_channels()
        if ch is None:
            ui.notify("No channel selected", type="warning")
            return
        try:
            session.reset(ch, bitrate=state.bitrate)
            update_chrome()
            ui.notify("Reset (session restarted)", type="info")
            return
        except Exception as first_exc:
            session.stop()
            update_chrome()
            ch2 = refresh_channels(prefer=ch)
            if ch2 is None:
                ui.notify(f"Reset failed: {first_exc}", type="negative")
                return
            try:
                session.start(ch2, bitrate=state.bitrate)
                update_chrome()
                ui.notify("Reset (after channel refresh)", type="info")
            except Exception as exc:
                session.stop()
                update_chrome()
                ui.notify(f"Reset failed: {exc}", type="negative")

    def do_quit() -> None:
        session.stop()
        ui.notify("Shutting down…", type="info")
        app.shutdown()

    def do_apply_listen() -> None:
        raw_host = (host_input.value or "").strip() or "127.0.0.1"
        try:
            new_port = int(port_input.value)
        except (TypeError, ValueError):
            ui.notify("Port must be an integer 1–65535", type="negative")
            return
        if not (1 <= new_port <= 65535):
            ui.notify("Port must be between 1 and 65535", type="negative")
            return
        if raw_host == state.host and new_port == state.port:
            ui.notify(
                f"Already listening on http://{state.host}:{state.port}/", type="info"
            )
            return
        state._relaunch = {
            "host": raw_host,
            "port": new_port,
            "config_path": state.config_path,
            "open_browser": state.open_browser,
            **state.cli_overrides,
        }
        session.stop()
        ui.notify(f"Restarting on http://{raw_host}:{new_port}/ …", type="info")
        app.shutdown()

    def switch_tab(name: str) -> None:
        pane_signals.set_visibility(name == "signals")
        pane_ecu.set_visibility(name == "ecu")
        pane_diag.set_visibility(name == "diagnostics")
        pane_traffic.set_visibility(name == "traffic")
        pane_faults.set_visibility(name == "faults")
        pane_scen.set_visibility(name == "scenarios")
        for btn, key in (
            (tab_signals, "signals"),
            (tab_ecu, "ecu"),
            (tab_diag, "diagnostics"),
            (tab_traffic, "traffic"),
            (tab_faults, "faults"),
            (tab_scen, "scenarios"),
        ):
            btn.classes(remove="active")
            if key == name:
                btn.classes(add="active")
        if name == "traffic":
            on_traffic_shown()

    last_health = [BusHealth.OK]

    def update_chrome() -> None:
        st = session.stats()
        n_requests = len(session.recent_requests())
        logs_tab_pill.set_text(f"{n_requests} Request{'' if n_requests == 1 else 's'}")
        faults_on = active_faults(sig, session.faults)
        faults_tab_pill.set_text(f"{len(faults_on)} Active" if faults_on else "None")
        if faults_on:
            faults_tab_pill.classes(add="warn")
            foot_faults.set_text(f"⚠ Faults: {len(faults_on)} active")
        else:
            faults_tab_pill.classes(remove="warn")
        foot_faults.set_visibility(bool(faults_on))
        runner = state.runner
        if runner.active and runner.scenario is not None:
            icon = "▶" if runner.state is RunState.RUNNING else "⏸"
            clock = f"{format_time(runner.elapsed())} / {format_time(runner.scenario.duration)}"
            scen_tab_pill.set_text(f"{icon} {format_time(runner.elapsed())}")
            scen_tab_pill.set_visibility(True)
            foot_scen.set_text(f"{icon} Scenario: {runner.scenario.name} {clock}")
            scen_banner_text.set_text(
                f"Scenario “{runner.scenario.name}” is {runner.state.value} ({clock}). "
                "It changes these values; what you set here may be overwritten by its next step."
            )
        else:
            scen_tab_pill.set_visibility(False)
        foot_scen.set_visibility(runner.active)
        scen_banner.set_visibility(runner.active)
        stopped_banner.set_visibility(not st.running)
        pane_signals.classes(
            remove="ecu-stopped", add="" if st.running else "ecu-stopped"
        )
        if st.running and session.faults.silent:
            # Silent is on purpose: say so instead of a bus-health state (nothing is sent).
            top_pill.classes(remove="stopped running error", add="warn")
            top_status.set_text("Silent (fault)")
            last_health[0] = st.bus_health
            btn_start.disable()
            btn_stop.enable()
        elif st.running:
            health_text = BUS_HEALTH_TEXT.get(st.bus_health)
            if health_text is None:
                top_pill.classes(remove="stopped warn error", add="running")
                top_status.set_text("Running")
            else:
                level = "error" if st.bus_health in BUS_HEALTH_ERRORS else "warn"
                top_pill.classes(remove="stopped running warn error", add=level)
                top_status.set_text(health_text[0])
                if st.bus_health is not last_health[0]:
                    ui.notify(health_text[1], type="warning", timeout=15000, close_button=True)
            last_health[0] = st.bus_health
            btn_start.disable()
            btn_stop.enable()
        else:
            last_health[0] = BusHealth.OK
            top_pill.classes(remove="running warn error", add="stopped")
            top_status.set_text("Stopped")
            btn_start.enable()
            btn_stop.disable()
        foot_peers.set_text(f"Other nodes: {st.peers}")
        claim_chip = state.ui_refs.get("claim_chip")
        claim_label = state.ui_refs.get("claim_label")
        if claim_chip is not None and claim_label is not None:
            if st.running and st.address_claimed:
                claim_chip.classes(remove="stopped", add="running")
                claim_label.set_text("NODE ONLINE · CLAIMED")
            else:
                claim_chip.classes(remove="running", add="stopped")
                claim_label.set_text("NODE OFFLINE")
        port_badge.set_text(f"{state.host}:{state.port} ✓")
        stat_uptime.set_text(_fmt_uptime(st.uptime_s))
        stat_tx.set_text(str(st.tx_count))
        load = 0.0 if not st.running else st.load_pct
        stat_load.set_text(f"{load:.1f}%")
        load_fill.style(f"width:{min(100.0, load):.0f}%")
        load_level = "high" if load >= 80 else "mid" if load >= 50 else ""
        load_fill.classes(remove="mid high", add=load_level)
        foot_tx.set_text(f"TX Broadcast: {st.tx_count} frames")
        foot_bitrate.set_text(f"{st.bitrate // 1000} kbit/s")
        ecu_bitrate = state.ui_refs.get("ecu_bitrate")
        if ecu_bitrate is not None:
            ecu_bitrate.set_text(f"{st.bitrate // 1000} kbit/s")
        foot_sa.set_text(f"SA: 0x{st.sa:02X}")
        c = st.active_dtcs
        if c > 0:
            foot_dtc.set_text(f"Active Faults: {c} DTCs")
            foot_dtc.classes(add="warn")
        else:
            foot_dtc.set_text("Active Faults: 0 DTCs")
            foot_dtc.classes(remove="warn")
        pill = state.ui_refs.get("diag_tab_pill")
        if pill is not None:
            pill.set_text(f"{c} Active")
            pill.set_visibility(c > 0)

    def refresh_payloads() -> None:
        payloads = all_payloads(sig)
        for key, label in state.payload_labels.items():
            label.set_text(payloads[key])
            try:
                label.update()
            except Exception:
                pass

    sig.clear_listeners()
    sig.on_change(refresh_payloads)

    mode_select.on_value_change(on_mode_change)
    channel_select.on_value_change(on_channel_change)
    bitrate_select.on_value_change(on_bitrate_change)
    refresh_btn.on_click(refresh_channels)
    btn_start.on_click(do_start)
    btn_stop.on_click(do_stop)
    btn_reset.on_click(do_reset)
    btn_quit.on_click(do_quit)
    btn_apply_port.on_click(do_apply_listen)
    btn_settings.on_click(settings_dialog.open)
    tab_signals.on_click(lambda: switch_tab("signals"))
    tab_ecu.on_click(lambda: switch_tab("ecu"))
    tab_diag.on_click(lambda: switch_tab("diagnostics"))
    tab_traffic.on_click(lambda: switch_tab("traffic"))
    tab_faults.on_click(lambda: switch_tab("faults"))
    tab_scen.on_click(lambda: switch_tab("scenarios"))

    ui.timer(0.2, update_chrome)

    def _init_channels() -> None:
        refresh_channels()
        btn_stop.disable()
        refresh_payloads()

    ui.timer(0.3, _init_channels, once=True)
