"""CLI entry: --gui | --config | --list-channels with runtime commands."""

from __future__ import annotations

import argparse
import sys
import time
import warnings

from j1939_emulator import __version__
from j1939_emulator.bus.detect import (
    DetectedChannel,
    EmulationMode,
    detect_hardware,
    find_channel,
    resolve_channel,
)
from j1939_emulator.bus.session import EmulatorSession
from j1939_emulator.config import IGNITION_VALUES, load_config
from j1939_emulator.ecu_identity import vin_check_digit_warning
from j1939_emulator.meters_store import restore_meters
from j1939_emulator.pgn import all_payloads
from j1939_emulator.scenario import (
    RunState,
    ScenarioError,
    ScenarioRunner,
    find_scenario,
    format_time,
    list_scenarios,
    load_scenario,
)


def _quiet_third_party_noise() -> None:
    """Hide known third-party warnings that scare end users at startup."""
    warnings.filterwarnings(
        "ignore",
        message=".*doesn't match a supported version.*",
        module="requests",
    )


def format_channel_table(
    channels: list[DetectedChannel],
    *,
    mode: EmulationMode | str,
    current_uid: str | None = None,
) -> str:
    """Simple channel list: use the number with --channel."""
    mode_s = mode.value if isinstance(mode, EmulationMode) else str(mode)
    title = "Virtual" if mode_s == "virtual" else "Real"
    lines = [f"Available {title} CAN channels ({len(channels)}):", ""]
    if not channels:
        lines.append("  (none found — plug in an adapter, or use --mode virtual)")
        return "\n".join(lines)

    lines.append("  #   Adapter")
    lines.append("  --  -----------------------------------------------")
    for i, ch in enumerate(channels, start=1):
        mark = " (current)" if current_uid and ch.uid == current_uid else ""
        lines.append(f"  {i:<3} {ch.label}{mark}")

    lines.append("")
    lines.append("Put the number after --channel. Example:")
    lines.append(
        f"  python -m j1939_emulator --config examples/ecu.toml "
        f"--mode {mode_s} --channel 1 --bitrate 500000"
    )
    lines.append("")
    lines.append("At the > prompt you can also type:  channels   or   channel 1")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="j1939_emulator",
        description=f"SAE J1939 Vehicle Emulator {__version__}",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument(
        "--gui",
        action="store_true",
        help="Open NiceGUI in the browser (default http://127.0.0.1:8080)",
    )
    p.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="GUI bind host (default: 127.0.0.1)",
    )
    p.add_argument(
        "--port",
        type=int,
        default=8080,
        help="GUI HTTP port (default: 8080)",
    )
    p.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not auto-open the system browser in GUI mode",
    )
    p.add_argument(
        "--config",
        "-c",
        type=str,
        help="TOML ECU config",
    )
    p.add_argument(
        "--mode",
        choices=["real", "virtual"],
        help="Override bus emulation mode",
    )
    p.add_argument(
        "--channel",
        type=str,
        help="Bus channel number from --list-channels (e.g. 1) or short name (e.g. vcan0)",
    )
    p.add_argument(
        "--bitrate",
        type=int,
        choices=[125000, 250000, 500000, 1000000],
        help="Override bitrate",
    )
    p.add_argument(
        "--list-channels",
        "-l",
        action="store_true",
        help="List detected channels for --mode (default: virtual) and exit",
    )
    p.add_argument(
        "--no-start",
        action="store_true",
        help="Do not auto-start emulation in CLI mode",
    )
    p.add_argument(
        "--scenario",
        type=str,
        help="CLI mode: play this scenario after START (built-in name like drive-and-stop, or a .toml path)",
    )
    return p


_HELP_TEXT = """\
channels [real|virtual]  — list adapters; use the number with --channel / channel
channel [N]              — show current channel or select by number (e.g. channel 1)
mode [real|virtual]      — show or set emulation mode
bitrate [Hz]             — show or set bitrate (125000|250000|500000|1000000)
info                     — dump runtime config (script/cloud friendly)
status                   — uptime / TX / load / claim / DTCs / bus health / other nodes
payloads                 — current PGN hex
requests [clear]         — Requests (PGN 59904) from other nodes and how they were answered
trace [N]                — last N lines (default 40) of the J1939 trace and its file path
ignition [on|run]        — show or set ignition: on = key ON, engine off; run = engine running
get <key>                — read SPN (e.g. get eec1.spn190_rpm)
set <key> <value>        — change SPN (e.g. set eec1.spn190_rpm 2100)
vin [value]              — show or set 17-char VIN
dtc [list]               — configured DTCs and which are active
dtc <n|spnX_fmiY|all> on|off — inject/clear DM1 faults (n = number in dtc list)
scenario                 — scenario status; scenario list | run <name|file> | pause | resume | stop
stop | start | reset | help | quit"""


def _dtc_states(diagnostics) -> str:
    """Active DTCs for status lines, e.g. "spn110_fmi3" or "none"."""
    return ",".join(d.key for d in diagnostics.active) or "none"


def _ignition_name(signals) -> str:
    return "run" if signals.engine_running else "on (engine off)"


def _scenario_command(runner: ScenarioRunner, rest: list[str]) -> None:
    """scenario [list | run <name|file> | pause | resume | stop]; no argument = status."""
    sub = rest[0].lower() if rest else "status"
    if sub == "list":
        for label, path in list_scenarios():
            try:
                s = load_scenario(path)
                print(f"{path.stem:<24} {format_time(s.duration):>7}  {s.name}  [{label.split(':')[0]}]")
            except ScenarioError as exc:
                print(f"{path.stem:<24}   error  {exc}")
        return
    if sub == "run":
        if len(rest) < 2:
            print("usage: scenario run <name|file.toml>  (see: scenario list)")
            return
        try:
            scenario = load_scenario(find_scenario(rest[1]))
            runner.start(scenario)
        except (ScenarioError, RuntimeError) as exc:
            print(f"error: {exc}")
            return
        print(f"scenario {scenario.name!r} running: {len(scenario.steps)} steps, {format_time(scenario.duration)}")
        return
    if sub in ("pause", "resume", "stop"):
        getattr(runner, sub)()
    s = runner.scenario
    if s is None:
        print("no scenario run yet (scenario list, scenario run <name>)")
        return
    nxt = s.steps[runner.done] if runner.active and runner.done < len(s.steps) else None
    extra = f" error={runner.error}" if runner.state is RunState.FAILED else ""
    print(
        f"scenario={s.name!r} state={runner.state.value} "
        f"time={format_time(runner.elapsed())}/{format_time(s.duration)} "
        f"steps={runner.done}/{len(s.steps)}{extra}"
        + (f" next=@{format_time(nxt.at)} {'; '.join(nxt.describe())}" if nxt else "")
    )


def main(argv: list[str] | None = None) -> int:
    _quiet_third_party_noise()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.gui:
        if not (1 <= int(args.port) <= 65535):
            print("error: --port must be between 1 and 65535", file=sys.stderr)
            return 2
        from j1939_emulator.gui.app import run_gui

        run_gui(
            config_path=args.config,
            host=args.host,
            port=int(args.port),
            open_browser=not args.no_browser,
            mode_override=args.mode,
            channel_override=args.channel,
            bitrate_override=args.bitrate,
        )
        return 0

    if args.list_channels:
        mode = EmulationMode(args.mode or "virtual")
        channels = detect_hardware(mode=mode, timeout=6.0)
        print(format_channel_table(channels, mode=mode))
        return 0

    if not args.config and not (args.mode or args.channel or args.bitrate):
        parser.print_help()
        print(
            "\nExamples:\n"
            "  python -m j1939_emulator --list-channels --mode virtual\n"
            "  python -m j1939_emulator --list-channels --mode real\n"
            "  python -m j1939_emulator --gui\n"
            "  python -m j1939_emulator --config examples/ecu.toml\n"
            "  python -m j1939_emulator --config examples/ecu.toml "
            "--mode real --channel 1 --bitrate 500000\n"
            "\nAt the > prompt: channels | channel 1 | mode | bitrate | info | "
            "get/set | vin | dtc | status | help\n",
            file=sys.stderr,
        )
        return 0

    return run_cli(args)


def run_cli(args: argparse.Namespace) -> int:
    if args.config:
        cfg = load_config(args.config)
        signals = cfg.signals
        identity = cfg.identity
        diagnostics = cfg.diagnostics
        mode = cfg.bus.mode
        channel_name = cfg.bus.channel
        bitrate = cfg.bus.bitrate
        start = cfg.start_on_launch and not args.no_start
        persist_meters = cfg.persist_meters
    else:
        from j1939_emulator.diagnostics import DiagnosticState
        from j1939_emulator.ecu_identity import EcuIdentity
        from j1939_emulator.pgn import SignalState

        signals = SignalState()
        identity = EcuIdentity()
        diagnostics = DiagnosticState()
        mode = EmulationMode(args.mode or "virtual")
        channel_name = args.channel or "vcan0"
        bitrate = args.bitrate or 500_000
        start = not args.no_start
        persist_meters = True

    if persist_meters and restore_meters(signals, identity.vin):
        print(
            f"restored meters for {identity.vin}: "
            f"odometer={signals.spn245_total_mi:.1f} mi engine_hours={signals.spn247_engine_hours:.2f} h"
        )

    if args.mode:
        mode = EmulationMode(args.mode)
    if args.channel:
        channel_name = args.channel
    if args.bitrate:
        bitrate = args.bitrate

    try:
        channel = find_channel(mode, channel_name)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print(
            format_channel_table(detect_hardware(mode=mode, timeout=6.0), mode=mode),
            file=sys.stderr,
        )
        print(
            "\nList channels first:\n"
            f"  python -m j1939_emulator --list-channels --mode {mode.value}",
            file=sys.stderr,
        )
        return 2

    session = EmulatorSession(
        signals=signals,
        identity=identity,
        diagnostics=diagnostics,
        bitrate=bitrate,
        mode=mode,
        persist_meters=persist_meters,
    )
    print(
        f"j1939-emulator {__version__}  mode={mode.value} "
        f"channel={channel.label!r} bitrate={bitrate} vin={identity.vin}"
    )
    if warning := vin_check_digit_warning(identity.vin):
        print(f"warning: {warning}")
    print(
        "Commands: channels | channel | mode | bitrate | info | "
        "get/set | vin | dtc | scenario | status | payloads | requests | trace | stop/start/reset | help | quit"
    )

    if start:
        try:
            session.start(channel, bitrate=bitrate)
            print("STARTED")
            print(
                f"claimed={session.address_claimed} "
                f"active_dtcs={session.diagnostics.active_count}"
            )
        except Exception as exc:
            print(f"error: failed to start: {exc}", file=sys.stderr)
            return 3

    runner = ScenarioRunner(session)
    if args.scenario:
        if not session.running:
            print("error: --scenario needs a running ECU (leave out --no-start)", file=sys.stderr)
            return 2
        _scenario_command(runner, ["run", args.scenario])

    try:
        while True:
            try:
                line = input("> ").strip()
            except EOFError:
                print()
                break
            if not line:
                continue
            parts = line.split(maxsplit=2)
            cmd = parts[0].lower()
            rest = parts[1:]

            if cmd in ("quit", "exit", "q"):
                break
            if cmd == "help":
                print(_HELP_TEXT)
                continue
            if cmd in ("channels", "ls", "list"):
                list_mode = mode
                if rest:
                    m = rest[0].lower()
                    if m not in ("real", "virtual"):
                        print("usage: channels [real|virtual]")
                        continue
                    list_mode = EmulationMode(m)
                chs = detect_hardware(mode=list_mode, timeout=6.0)
                print(
                    format_channel_table(
                        chs, mode=list_mode, current_uid=channel.uid
                    )
                )
                continue
            if cmd == "channel":
                if not rest:
                    print(f"channel={channel.label!r} mode={mode.value}")
                    continue
                needle = rest[0] if len(rest) == 1 else " ".join(rest)
                try:
                    new_ch = find_channel(mode, needle)
                except ValueError as exc:
                    print(f"error: {exc}")
                    print(
                        format_channel_table(
                            detect_hardware(mode=mode, timeout=6.0),
                            mode=mode,
                            current_uid=channel.uid,
                        )
                    )
                    continue
                was_running = session.running
                if was_running:
                    session.stop()
                    print("STOPPED")
                channel = new_ch
                channel_name = new_ch.uid
                print(f"ok channel={channel.label!r}")
                if was_running:
                    try:
                        session.start(channel, bitrate=bitrate)
                        print("STARTED")
                    except Exception as exc:
                        print(f"error: {exc}")
                continue
            if cmd == "mode":
                if not rest:
                    print(f"mode={mode.value}")
                    continue
                m = rest[0].lower()
                if m not in ("real", "virtual"):
                    print("usage: mode real|virtual")
                    continue
                new_mode = EmulationMode(m)
                if new_mode is mode:
                    print(f"mode={mode.value}")
                    continue
                was_running = session.running
                if was_running:
                    session.stop()
                    print("STOPPED")
                mode = new_mode
                session.mode = mode
                # Pick a sensible default channel for the new mode
                chs = detect_hardware(mode=mode, timeout=6.0)
                if not chs:
                    print(f"ok mode={mode.value} (no channels — run: channels)")
                    continue
                channel = chs[0]
                channel_name = channel.uid
                print(f"ok mode={mode.value} channel={channel.label!r}")
                print(format_channel_table(chs, mode=mode, current_uid=channel.uid))
                if was_running:
                    try:
                        session.start(channel, bitrate=bitrate)
                        print("STARTED")
                    except Exception as exc:
                        print(f"error: {exc}")
                continue
            if cmd == "bitrate":
                if not rest:
                    print(f"bitrate={bitrate}")
                    continue
                try:
                    br = int(rest[0])
                except ValueError:
                    print("usage: bitrate 125000|250000|500000|1000000")
                    continue
                if br not in (125_000, 250_000, 500_000, 1_000_000):
                    print("error: bitrate must be 125000|250000|500000|1000000")
                    continue
                bitrate = br
                session.bitrate = br
                print(f"ok bitrate={bitrate} (applies on next start/reset if stopped)")
                if session.running:
                    try:
                        session.stop()
                        session.start(channel, bitrate=bitrate)
                        print("RESET")
                    except Exception as exc:
                        session.stop()
                        chs = detect_hardware(mode=mode, timeout=6.0)
                        retry = resolve_channel(chs, uid=channel.uid, previous=channel)
                        if retry is not None:
                            channel = retry
                            channel_name = channel.uid
                            try:
                                session.start(channel, bitrate=bitrate)
                                print(f"RESET (after refresh → {channel.label!r})")
                                continue
                            except Exception as exc2:
                                session.stop()
                                print(f"error: {exc2}")
                                continue
                        print(f"error: {exc}")
                continue
            if cmd == "info":
                st = session.stats()
                print(
                    f"version={__version__}\n"
                    f"mode={mode.value}\n"
                    f"channel={channel.label}\n"
                    f"bitrate={bitrate}\n"
                    f"running={st.running}\n"
                    f"claimed={st.address_claimed}\n"
                    f"sa=0x{st.sa:02X}\n"
                    f"vin={session.identity.vin}\n"
                    f"dtcs={_dtc_states(session.diagnostics)}\n"
                    f"tx={st.tx_count}\n"
                    f"load_pct={st.load_pct:.1f}\n"
                    f"bus={st.bus_health.value}\n"
                    f"peers={st.peers}"
                )
                continue
            if cmd == "scenario":
                _scenario_command(runner, rest)
                continue
            if cmd == "status":
                st = session.stats()
                mm = int(st.uptime_s) // 60
                ss = int(st.uptime_s) % 60
                print(
                    f"running={st.running} claimed={st.address_claimed} "
                    f"uptime={mm:02d}:{ss:02d} tx={st.tx_count} "
                    f"load={st.load_pct:.1f}% bitrate={st.bitrate} "
                    f"dtcs={st.active_dtcs} bus={st.bus_health.value} peers={st.peers} "
                    f"ignition={_ignition_name(session.signals)} "
                    f"vin={session.identity.vin} "
                    f"channel={channel.label!r}"
                )
                continue
            if cmd == "ignition":
                if rest:
                    choice = rest[0].lower()
                    if choice not in IGNITION_VALUES:
                        print("usage: ignition [on|run]")
                        continue
                    session.signals.set_ignition(IGNITION_VALUES[choice])
                print(f"ignition={_ignition_name(session.signals)}")
                continue
            if cmd == "requests":
                if rest and rest[0] == "clear":
                    session.clear_requests()
                    print("ok")
                    continue
                events = session.recent_requests()
                if not events:
                    print("no requests received yet")
                for ev in events:
                    stamp = time.strftime("%H:%M:%S", time.localtime(ev.at)) + f".{int(ev.at * 1000) % 1000:03d}"
                    name = f" {ev.pgn_name}" if ev.pgn_name else ""
                    print(
                        f"{stamp}  0x{ev.src:02X}->0x{ev.dest:02X}  "
                        f"PGN {ev.pgn}{name}  {ev.result or 'pending'}"
                    )
                continue
            if cmd == "trace":
                trace = session.trace
                if trace is None:
                    print("no trace yet: start the ECU first")
                    continue
                n = int(rest[0]) if rest and rest[0].isdigit() else 40
                _count, lines = trace.recent()
                for line in lines[-n:]:
                    print(line)
                print(f"file: {trace.path or 'not available'}")
                continue
            if cmd == "payloads":
                for name, hex_s in all_payloads(session.signals).items():
                    print(f"{name}: {hex_s}")
                continue
            if cmd == "get":
                if not rest:
                    print("usage: get <key>")
                    continue
                try:
                    print(f"{rest[0]}={session.signals.get_spn(rest[0])}")
                except KeyError as exc:
                    print(f"error: {exc}")
                continue
            if cmd == "vin":
                if not rest:
                    print(f"vin={session.identity.vin}")
                    continue
                try:
                    cleaned = session.set_vin(
                        rest[0] if len(rest) == 1 else " ".join(rest)
                    )
                    print(f"ok vin={cleaned}")
                    if warning := vin_check_digit_warning(cleaned):
                        print(f"warning: {warning}")
                except ValueError as exc:
                    print(f"error: {exc}")
                continue
            if cmd == "dtc":
                if len(rest) < 2:
                    for i, d in enumerate(session.diagnostics.dtcs, 1):
                        state_txt = f"ACTIVE (OC {d.oc})" if d.active else "inactive"
                        print(f"{i:>2}. {d.key:<16} {d.lamp:<8} {state_txt:<16} {d.name}")
                    print("usage: dtc <n|spnX_fmiY|all> <on|off>")
                    continue
                which, state_s = rest[0].lower(), rest[1].lower()
                active = state_s in ("on", "1", "true", "inject")
                if state_s in ("off", "0", "false", "clear"):
                    active = False
                elif state_s not in ("on", "1", "true", "inject"):
                    print("error: state must be on|off")
                    continue
                dtcs = session.diagnostics.dtcs
                if which in ("all", "both"):
                    if active:
                        session.inject_all_dtcs()
                    else:
                        session.clear_all_dtcs()
                else:
                    if which.isdigit() and 1 <= int(which) <= len(dtcs):
                        which = dtcs[int(which) - 1].key
                    try:
                        session.set_dtc(which, active)
                    except KeyError:
                        print(f"error: no DTC {which!r}; see dtc list")
                        continue
                print(f"ok dtcs={_dtc_states(session.diagnostics)}")
                continue
            if cmd == "stop":
                session.stop()
                print("STOPPED")
                continue
            if cmd == "start":
                try:
                    session.start(channel, bitrate=bitrate)
                    print("STARTED")
                except Exception as exc:
                    session.stop()
                    chs = detect_hardware(mode=mode, timeout=6.0)
                    retry = resolve_channel(chs, uid=channel.uid, previous=channel)
                    if retry is None:
                        print(f"error: {exc}")
                        continue
                    channel = retry
                    channel_name = channel.uid
                    try:
                        session.start(channel, bitrate=bitrate)
                        print(f"STARTED (after refresh → {channel.label!r})")
                    except Exception as exc2:
                        session.stop()
                        print(f"error: {exc2}")
                continue
            if cmd == "reset":
                try:
                    session.reset(channel, bitrate=bitrate)
                    print("RESET")
                except Exception as exc:
                    session.stop()
                    chs = detect_hardware(mode=mode, timeout=6.0)
                    retry = resolve_channel(chs, uid=channel.uid, previous=channel)
                    if retry is None:
                        print(f"error: {exc}")
                        continue
                    channel = retry
                    channel_name = channel.uid
                    try:
                        session.start(channel, bitrate=bitrate)
                        print(f"RESET (after refresh → {channel.label!r})")
                    except Exception as exc2:
                        session.stop()
                        print(f"error: {exc2}")
                continue
            if cmd == "set":
                if len(rest) < 2:
                    print("usage: set <key> <value>")
                    continue
                key, value = rest[0], rest[1]
                try:
                    session.signals.set_spn(key, value)
                    print(f"ok {key}={value}")
                except (KeyError, ValueError) as exc:
                    print(f"error: {exc}")
                continue
            print(f"unknown command: {cmd}  (type help)")
    except KeyboardInterrupt:
        print("\nInterrupted")
    finally:
        runner.stop()
        session.stop()
        print("Bus closed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
