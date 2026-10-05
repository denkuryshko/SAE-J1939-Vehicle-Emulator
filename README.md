# SAE J1939 Vehicle Emulator

SAE J1939 vehicle ECU emulator for ELD and telematics QA.
It simulates engine speed, vehicle speed, odometer, engine hours, VIN, address claim and diagnostic faults on a **virtual** or **physical** CAN bus, so you can test an ELD on the bench without a truck.

Built with **python-can**, **can-j1939** and **NiceGUI**.

**Requirements:** Python **3.11+** · Windows, Linux or macOS · a browser for the GUI (Chrome, Edge or Safari)

### What you get

| Area | Capability |
|------|------------|
| **Bus** | Real hardware auto-detect or Virtual (`vcan0` / `vcan1` / `vcan2`) · START / STOP / RESET · live TX stats |
| **Signals** | 4 cyclic PGNs with live controls and presets · odometer and engine hours count up automatically while running |
| **ECU / VIN** | Single node SA `0x00` · J1939-81 address claim · VIN on PGN 65260, `*`-terminated |
| **Requests** | Answers Request (PGN 59904), global or to SA `0x00`, for VIN and all broadcast PGNs |
| **Diagnostics** | 2 injectable DTCs on DM1 (PGN 65226): SPN 110 / FMI 3, SPN 190 / FMI 0 |
| **UI** | Web GUI (default `http://127.0.0.1:8080`) or interactive CLI |

### Broadcast PGNs

| PGN | Name | CAN ID | Cycle | Signal (config key, unit) | Default |
|-----|------|--------|-------|---------------------------|---------|
| 61444 | EEC1: Electronic Engine Controller 1 | `0x0CF00400` | 20 ms | Engine Speed, SPN 190 (`eec1.spn190_rpm`, rpm) | 0 |
| 65265 | CCVS: Cruise Control / Vehicle Speed | `0x18FEF100` | 100 ms | Wheel-Based Vehicle Speed, SPN 84 (`ccvs.spn84_speed_mph`, mph) | 0 |
| 65248 | VD: Vehicle Distance | `0x18FEE000` | 1000 ms | Total Vehicle Distance, SPN 245 (`vd.spn917_total_mi`, mi) | 248912.4 |
| 65253 | HOURS: Engine Hours, Revolutions | `0x18FEE500` | 1000 ms | Engine Total Hours of Operation, SPN 247 (`hours.spn247_engine_hours`, h) | 10000 |

All other SPNs in these PGNs are sent as *not available* (`0xFF`).

> The GUI and the config key label total distance as "SPN 917" for historical reasons. On the wire it is encoded in PGN 65248 bytes 5–8, which is SPN 245 (0.125 km/bit).

### Automatic odometer and engine hours

While the ECU is running (after **START**):

- **Engine hours** (SPN 247) increase in real time whenever Engine Speed > 0 rpm.
- **Odometer** (total distance) increases by `vehicle speed × elapsed time`. For example, 60 mph for one minute adds 1 mile.

Both stop counting at 0 rpm / 0 mph and after **STOP**. You can set either value by hand at any time, and counting continues from the new value. Accumulated values are not saved between runs; each launch starts from the config or the defaults.

The CAN frames change in J1939 resolution steps: 0.05 h (3 minutes) for engine hours and 0.125 km (about 0.078 mi) for distance.

---

## Hardware setup

One supported CAN adapter is enough to run the emulator.

![J1939 Emulator hardware connections](docs/HardwareConnections.png)


**Tested on:** CANable / candleLight (candle / gs_usb, slcan), Vector VN1610

### Bench wiring checklist

A CAN frame is only delivered when at least one other node acknowledges (ACKs) it. Most ELDs connect to the truck in **listen-only** mode and never send an ACK. On a bench with just the adapter and an ELD, the emulator's frames may therefore never get through.

- Terminate the bus with **120 Ω at both ends**. With power off, CAN-H to CAN-L should measure about **60 Ω**.
- If the ELD is listen-only, add a third node in normal mode (a second adapter, or a Vector VN1610 / TSMaster) so frames get ACKed.
- J1939 9-pin Deutsch connector: **C = CAN-H**, **D = CAN-L**. Check that H and L are not swapped.
- The ELD and the emulator must use the same bitrate (most trucks use **250 kbit/s**, newer ones 500 kbit/s).
- Close other CAN tools (Cangaroo, TSMaster, etc.) that may hold the adapter before pressing **START**.

---

## 1. Clone and set up

Run every command from the **repository root** (`j1939-emulator`), not from the inner `j1939_emulator` package folder.

### Windows PowerShell

```powershell
git clone https://github.com/denkuryshko/j1939-emulator.git
cd j1939-emulator

python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If activation fails with `running scripts is disabled`:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\.venv\Scripts\Activate.ps1
```

Or skip activation and call the venv Python directly, e.g. `.\.venv\Scripts\python.exe -m pip install …`.

### Windows Command Prompt (cmd.exe)

```bat
git clone https://github.com/denkuryshko/j1939-emulator.git
cd j1939-emulator

python -m venv .venv
.venv\Scripts\activate.bat
```

### Linux / macOS

```bash
git clone https://github.com/denkuryshko/j1939-emulator.git
cd j1939-emulator

python3 -m venv .venv
source .venv/bin/activate
```

---

## 2. Install

Stay in the repository root with the venv **activated**.

### Quick start (Virtual bus only)

```bash
python -m pip install --upgrade pip
python -m pip install -e .
```

This installs the app plus **can-j1939**, **nicegui**, **cantools**, **libusb-package** and a base **python-can**. On **Windows**, **pywin32** is installed too (required by can-j1939). Virtual Emulation works right away; no CAN adapter is needed.

### Full install (Real hardware adapters)

Use this for candleLight, Peak, Vector, etc. Vendor **OS drivers** are still required for those devices.

**Windows**

```powershell
python -m pip install --upgrade pip
python -m pip install -e . "python-can[gs-usb,serial,candle,pcan,neovi,canalystii,nixnet,seeedstudio,cvector,remote,sontheim,canine,zlgcan,viewer,mf4,multicast,pywin32]"
```

**Linux / macOS**

```bash
python -m pip install --upgrade pip
python -m pip install -e . "python-can[gs-usb,serial,candle,pcan,neovi,canalystii,nixnet,seeedstudio,cvector,remote,sontheim,canine,zlgcan,viewer,mf4,multicast]"
```

Optional CANtact support (needs [Rust](https://rustup.rs)):

```bash
python -m pip install "python-can[cantact]"
```

---

## 3. Run: GUI

```bash
python -m j1939_emulator --gui
```

The default browser opens at `http://127.0.0.1:8080`. To start from a config file:

```bash
python -m j1939_emulator --gui --config my_ecu.toml
```

**Windows shortcut:** double-click `run_gui.bat`. It lists the detected CAN adapters, then opens the GUI with `my_ecu.toml`. Make sure `[bus] channel` in `my_ecu.toml` matches the adapter number it prints.

Other options: `--host` / `--port` to change the address, `--no-browser` to skip auto-open. You can also change **Host** / **Port** in the top bar and click **Apply** (the UI restarts). **QUIT** stops the server.

### Workflow

1. **Bus config:** choose **Virtual Emulation** (no hardware) or **Real Hardware Emulation**, then the channel and bitrate.
2. Click **START**. The ECU claims SA `0x00`, broadcasts the VIN and starts the cyclic PGNs.
3. **Signals** tab: drag sliders or use presets (e.g. Engine Speed **0 rpm / Idle 650 / Cruise 1250 / Rated 2100**). Odometer and engine hours count up on their own while running.
4. Click **Details** on any PGN card to see the technical data: PGN, CAN ID, cycle time (editable), live CAN payload, DLC and priority. The panels are collapsed by default.
5. **ECU & Vehicle (VIN)** tab: edit the VIN and click **Set** (rebroadcasts immediately), copy it, view NAME / SA. The chip shows when the node is claimed.
6. **Diagnostics** tab: inject or clear the two DTCs (sent on DM1 while running).
7. Click **QUIT** when finished.

### Bus modes

| Mode | Channels | Hardware |
|------|----------|----------|
| **Virtual Emulation** | `vcan0`, `vcan1`, `vcan2` (python-can software bus) | Not required |
| **Real Hardware Emulation** | Detected adapters (candleLight, Vector VN1610, …) | Adapter must be plugged in; unplugged devices do not appear |

---

## 4. Run: CLI

```bash
python -m j1939_emulator --config examples/ecu.toml
```

By default this uses the Virtual channel `vcan0` at 500 kbit/s (see `examples/ecu.toml`) and starts immediately. Odometer and engine hours count in CLI mode too.

### Choosing a channel

List adapters, then pass the **number** to `--channel`:

```bash
python -m j1939_emulator --list-channels --mode real
python -m j1939_emulator --config my_ecu.toml --mode real --channel 1 --bitrate 250000
```

Example output:

```text
Available Real CAN channels (3):

  #   Adapter
  --  -----------------------------------------------
  1   candleLight  (serial ...20393630)
  2   serial  ch=COM5
  3   serial  ch=COM8
```

For Virtual mode you can also use the names `vcan0`, `vcan1`, `vcan2`. Use `--no-start` to open the prompt without starting emulation.

### Commands at the `>` prompt

| Command | Meaning |
|---------|---------|
| `channels [real\|virtual]` | List adapters; note the **#** to use with `--channel` / `channel` |
| `channel [N]` | Show the current channel or select one by number |
| `mode [real\|virtual]` | Show or change emulation mode |
| `bitrate [Hz]` | Show or set bitrate (`125000` … `1000000`) |
| `info` | Dump runtime config as `key=value` (for scripts and automation) |
| `status` / `payloads` | Live stats / current PGN hex |
| `get <key>` / `set <key> <value>` | Read / change a signal (keys below) |
| `vin [value]` | Show or set the VIN (rebroadcasts PGN 65260 if running) |
| `dtc 1\|2\|both on\|off` | Inject / clear DM1 faults |
| `stop` / `start` / `reset` / `help` / `quit` | Session control |

Signal keys for `get` / `set`:

```text
eec1.spn190_rpm             set eec1.spn190_rpm 650
ccvs.spn84_speed_mph        set ccvs.spn84_speed_mph 65
vd.spn917_total_mi          set vd.spn917_total_mi 250000
hours.spn247_engine_hours   set hours.spn247_engine_hours 12000
eec1.cycle_ms, ccvs.cycle_ms, vd.cycle_ms, hours.cycle_ms
```

---

## 5. Config file

See [`examples/ecu.toml`](examples/ecu.toml) (Virtual) and [`my_ecu.toml`](my_ecu.toml) (candleLight at 250 kbit/s). All fields:

```toml
[bus]
mode = "virtual"          # "real" | "virtual"
channel = "vcan0"         # adapter number from --list-channels, or vcan0/1/2
bitrate = 500000          # 125000 | 250000 | 500000 | 1000000
start_on_launch = true    # CLI: start immediately

[ecu]
source_address = 0x00
industry_group = 0
vehicle_system = 0
name = 0x0020000000000000

[vehicle]
vin = "1HTMMAAL7GH123456"

[diagnostics]
dtc_spn110_fmi3 = false   # SPN 110 / FMI 3: amber warning
dtc_spn190_fmi0 = false   # SPN 190 / FMI 0: red stop

[pgn.eec1]
enabled = true
cycle_ms = 20
spn190_rpm = 0

[pgn.ccvs]
enabled = true
cycle_ms = 100
spn84_speed_mph = 0

[pgn.vd]
enabled = true
cycle_ms = 1000
spn917_total_mi = 248912.4   # starting odometer, miles

[pgn.hours]
enabled = true
cycle_ms = 1000
spn247_engine_hours = 10000.0   # starting engine hours
```

Every `[pgn.*]` section is optional; missing values use the defaults from the table above. Set `enabled = false` to stop broadcasting a PGN.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---------|--------------------|
| ELD sees nothing; GUI still shows RUNNING | No node ACKs the frames. See the [bench wiring checklist](#bench-wiring-checklist): termination, a third ACKing node, H/L wiring, bitrate. |
| ELD sees engine data but no VIN | The ELD must be able to receive multi-packet BAM (PGN 60416 / 60160). VIN is broadcast on START and on **Set**, and sent again whenever the ELD requests PGN 65260. |
| `START failed` / `Cannot open device` | Another program holds the adapter, or the USB device has not been released yet. Close other CAN tools, wait a second and press START again. |
| Port 8080 already in use | `python -m j1939_emulator --gui --port 8090` |
| Adapter not listed | Check the vendor driver and USB cable, then click **Refresh** (GUI) or run `channels real` (CLI). |

---

## License

MIT, see [LICENSE](LICENSE).
