"""Application CSS for the NiceGUI pages. Design tokens live in :root; use var(--…), not hex."""

# Inter for the UI, JetBrains Mono for numbers, PGN/SPN, hex and the trace. Offline the
# browser falls back to system-ui / ui-monospace.
FONTS_HTML = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700'
    '&family=JetBrains+Mono:wght@400;500;600;700&display=swap">'
)

APP_CSS = """
:root {
  /* Type */
  --font-ui: "Inter", system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  --fs-12: 12px; --fs-13: 13px; --fs-14: 14px; --fs-16: 16px; --fs-20: 20px;

  /* Spacing grid */
  --sp-4: 4px; --sp-8: 8px; --sp-12: 12px; --sp-16: 16px; --sp-24: 24px; --sp-32: 32px;

  /* Colour */
  --bg: #F7F8FA;
  --surface: #FFFFFF;
  --border: #E3E6EB;
  --border-strong: #CDD2DA;
  --text: #1A1D23;
  --text-muted: #6B7280;
  --text-subtle: #9CA3AF;
  --accent: #2563EB;          /* interactive only: buttons, links, active tab, focus */
  --accent-soft: #EFF4FF;
  --accent-line: #BFD3FE;
  --ok: #16A34A;
  --ok-soft: #ECFDF3;
  --ok-line: #A6E3BC;
  --ok-text: #15803D;
  --warn: #D97706;
  --warn-soft: #FFF8EB;
  --warn-line: #FAD9A5;
  --warn-text: #B45309;
  --danger: #DC2626;
  --danger-soft: #FEF2F2;
  --danger-line: #FCA5A5;
  --danger-text: #B91C1C;

  /* Shape */
  --radius: 6px;
  --shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
  --focus-ring: 0 0 0 3px rgba(37, 99, 235, 0.18);
}
body {
  /* Quasar brand colours follow the tokens */
  --q-primary: var(--accent); --q-positive: var(--ok); --q-negative: var(--danger);
  --q-warning: var(--warn); --q-info: var(--accent);
}

*, *::before, *::after { box-sizing: border-box; }
body, .nicegui-content {
  font-family: var(--font-ui) !important;
  background-color: var(--bg) !important;
  color: var(--text);
  font-size: var(--fs-13);
  line-height: 1.5;
}
.q-page, .nicegui-content { padding: 0 !important; }
.font-mono, .font-mono .q-field__native, .font-mono input {
  font-family: var(--font-mono) !important; font-variant-numeric: tabular-nums;
}
.q-btn { text-transform: none; letter-spacing: normal; font-family: var(--font-ui); }
.q-field--outlined .q-field__control { border-radius: var(--radius); }
.q-field--outlined .q-field__control:before { border-color: var(--border-strong); }
.q-tooltip { font-size: var(--fs-12); border-radius: var(--radius); }

/* Shared building blocks */
.pane { display: flex; flex-direction: column; gap: var(--sp-16); }
.pane-head { border-bottom: 1px solid var(--border); padding-bottom: var(--sp-8); }
.pane-title { font-size: var(--fs-16); font-weight: 600; color: var(--text); }
.pane-sub, .text-sm-muted { font-size: var(--fs-12); color: var(--text-muted); }
.section-caption, .field-label {
  font-size: var(--fs-12); font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em;
  color: var(--text-muted);
}
.field-label { margin-bottom: var(--sp-4); display: block; }
.subpanel {
  background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius);
  padding: var(--sp-12);
}

.j1939-root { width: 100%; min-height: 100vh; display: flex; flex-direction: column; background: var(--bg); }
.topbar {
  min-height: 56px; height: auto; background: var(--surface); border-bottom: 1px solid var(--border);
  padding: var(--sp-8) var(--sp-16); display: flex; flex-wrap: wrap; align-items: center;
  justify-content: space-between; gap: var(--sp-8) var(--sp-12); flex-shrink: 0;
}
.brand-section {
  display: flex; align-items: center; gap: var(--sp-12); min-width: 0; flex: 1 1 auto;
}
.brand-icon { width: 32px; height: 32px; flex-shrink: 0; }
.brand-title {
  font-weight: 700; font-size: var(--fs-16); color: var(--text);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0;
}
.topbar-controls {
  display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-8) var(--sp-12);
  flex: 0 1 auto; justify-content: flex-end;
}
@media (max-width: 900px) {
  .brand-title { max-width: 260px; }
}
@media (max-width: 640px) {
  .brand-title { display: none; }
}
.badge-subtle {
  font-size: var(--fs-12); font-weight: 600; padding: 0 var(--sp-8); border-radius: var(--radius);
  background: var(--accent-soft); color: var(--accent); border: 1px solid var(--accent-line);
}
.status-pill {
  display: inline-flex; align-items: center; gap: var(--sp-8); padding: var(--sp-4) var(--sp-12);
  border-radius: var(--radius); font-size: var(--fs-12); font-weight: 600;
}
.status-pill.stopped { background: var(--bg); color: var(--text-muted); border: 1px solid var(--border-strong); }
.status-pill.running { background: var(--ok-soft); color: var(--ok-text); border: 1px solid var(--ok-line); }
.status-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.status-pill.stopped .status-dot { background: var(--text-subtle); }
.status-pill.running .status-dot { background: var(--ok); }
.status-pill.warn { background: var(--warn-soft); color: var(--warn-text); border: 1px solid var(--warn-line); }
.status-pill.warn .status-dot { background: var(--warn); }
.status-pill.error { background: var(--danger-soft); color: var(--danger-text); border: 1px solid var(--danger-line); }
.status-pill.error .status-dot { background: var(--danger); }

/* Top-bar ECU state: the first thing to read on the bench */
.status-pill.status-hero {
  font-size: var(--fs-13); padding: var(--sp-8) var(--sp-16); gap: var(--sp-8); border-width: 2px;
}
.status-hero .status-dot { width: 10px; height: 10px; }
.status-hero.stopped { background: var(--bg); color: var(--text-muted); border-color: var(--border-strong); }
.status-hero.running { background: var(--ok); color: var(--surface); border-color: var(--ok); }
.status-hero.running .status-dot { background: var(--surface); animation: status-pulse 1.4s ease-in-out infinite; }
.status-hero.warn { background: var(--warn); color: var(--surface); border-color: var(--warn); }
.status-hero.warn .status-dot { background: var(--surface); }
.status-hero.error { background: var(--danger); color: var(--surface); border-color: var(--danger); }
.status-hero.error .status-dot { background: var(--surface); }
@keyframes status-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }

.listen-group { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-4) var(--sp-8); }
.listen-group .field-label { margin: 0; }
.host-input { width: 120px; }
.port-input { width: 88px; }

.j1939-main {
  flex: 1; max-width: 2200px; width: 100%; margin: 0 auto; padding: var(--sp-16);
  display: flex; flex-direction: column; gap: var(--sp-12);
}
/* Tabs on the left, the Logs panel always visible on the right (below them on narrow screens) */
.workspace {
  display: grid; grid-template-columns: minmax(0, 1fr) minmax(400px, 36%); gap: var(--sp-12);
  align-items: start;
}
.work-main { display: flex; flex-direction: column; gap: var(--sp-12); min-width: 0; }
.work-logs { position: sticky; top: var(--sp-12); min-width: 0; }
.logs-panel {
  display: flex; flex-direction: column; gap: var(--sp-16);
  max-height: calc(100vh - 24px); overflow-y: auto;
}
.logs-live { font-size: var(--fs-12); font-weight: 600; color: var(--text); }
.logs-paused {
  font-size: var(--fs-12); font-weight: 600; padding: 0 var(--sp-8); border-radius: var(--radius);
  background: var(--warn-soft); color: var(--warn-text); border: 1px solid var(--warn-line);
}
/* The trace fills the rest of the window height in the side panel */
.trace-log { height: max(320px, calc(100vh - 420px)); font-family: var(--font-mono) !important; }
@media (max-width: 1100px) {
  .trace-log { height: 320px; }
  .workspace { grid-template-columns: minmax(0, 1fr); }
  .work-logs { position: static; }
  .logs-panel { max-height: none; }
}
.card {
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
  padding: var(--sp-12) var(--sp-16); box-shadow: var(--shadow);
}
.bus-bar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--sp-12); }
.bus-controls-group { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-16); }
.bus-caption { border-right: 1px solid var(--border); padding-right: var(--sp-8); }
.bus-field { flex: 0 1 auto; min-width: 0; }
.bus-select { width: 220px; max-width: 100%; }
.bus-field-wide .bus-select { width: 260px; }
.run-controls { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-8); }
.run-stats {
  display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-4) var(--sp-12);
  margin-left: var(--sp-12); font-size: var(--fs-12); color: var(--text-muted);
}
.run-stats .stat-value { font-weight: 600; color: var(--text); }
.run-stats .stat-value.ok { color: var(--ok-text); }
.run-stats .stat-sep { color: var(--border-strong); }
.vin-row { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-8); margin-top: var(--sp-4); }
.vin-input { flex: 1 1 210px; min-width: 0; font-weight: 600; text-transform: uppercase; }
.action-btn {
  height: 32px; padding: 0 var(--sp-12); font-size: var(--fs-13); font-weight: 600;
  border-radius: var(--radius); border: 1px solid transparent; cursor: pointer;
  display: inline-flex; align-items: center; gap: var(--sp-8);
}
.btn-start { background: var(--accent); color: var(--surface); border-color: var(--accent); }
.btn-stop { background: var(--surface); color: var(--danger-text); border-color: var(--border-strong); }
.btn-restart { background: var(--surface); color: var(--text); border-color: var(--border-strong); }
.btn-quit { background: var(--danger); color: var(--surface); border-color: var(--danger); }
.btn-disabled { opacity: 0.5; pointer-events: none; }
.action-btn:focus-visible, .tab-btn:focus-visible { box-shadow: var(--focus-ring); }

.tab-bar {
  display: flex; background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); overflow-x: auto;
}
.tab-btn {
  padding: var(--sp-12) var(--sp-16); font-size: var(--fs-13); font-weight: 500; background: transparent;
  border: none; border-bottom: 2px solid transparent; border-radius: 0; color: var(--text-muted); cursor: pointer;
  display: inline-flex; align-items: center; gap: var(--sp-8); white-space: nowrap;
}
.tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); font-weight: 600; }
.tab-pill {
  font-size: var(--fs-12); padding: 0 var(--sp-4); border-radius: var(--radius); background: var(--bg);
  color: var(--text-muted); border: 1px solid var(--border); margin-left: var(--sp-8);
}
.tab-btn.active .tab-pill { background: var(--accent-soft); color: var(--accent); border-color: var(--accent-line); }
.tab-pill.warn { background: var(--warn-soft); color: var(--warn-text); border-color: var(--warn-line); }
.logs-pill { margin-left: 0; }

.dtc-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--sp-12);
}
.dtc-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--sp-16);
  display: flex;
  flex-direction: column;
  gap: var(--sp-12);
}
.dtc-card.fault-amber { background: var(--warn-soft); border-color: var(--warn-line); border-left: 4px solid var(--warn); }
.dtc-card.fault-red { background: var(--danger-soft); border-color: var(--danger-line); border-left: 4px solid var(--danger); }
.dtc-name { font-weight: 600; font-size: var(--fs-13); color: var(--text); }
.dtc-foot { border-top: 1px solid var(--border); padding-top: var(--sp-8); }
.lamp-badge.red { background: var(--danger-soft); color: var(--danger-text); border-color: var(--danger-line); }
.lamp-badge.amber { background: var(--warn-soft); color: var(--warn-text); border-color: var(--warn-line); }
.dm1-alert {
  display: none; background: var(--warn-soft); border: 1px solid var(--warn-line); border-radius: var(--radius);
  padding: var(--sp-12); font-size: var(--fs-12); color: var(--warn-text);
}
.dm1-alert-title { font-weight: 600; }

.pgn-card {
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
  margin-bottom: var(--sp-8); overflow: hidden;
}
.pgn-header {
  padding: var(--sp-4) var(--sp-12); background: var(--bg); border-bottom: 1px solid var(--border);
  display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--sp-4) var(--sp-8);
}
.pgn-title-group { display: flex; align-items: center; gap: var(--sp-8); min-width: 0; flex: 1 1 260px; }
.badge-acronym {
  font-size: var(--fs-12); font-weight: 600; background: var(--text); color: var(--surface);
  padding: 0 var(--sp-8); border-radius: var(--radius); flex-shrink: 0;
}
.pgn-name {
  font-weight: 600; font-size: var(--fs-14); color: var(--text); min-width: 0;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.pgn-number { font-size: var(--fs-12); font-weight: 400; color: var(--text-subtle); white-space: nowrap; flex-shrink: 0; }
.pgn-header-right { display: flex; align-items: center; gap: var(--sp-8); margin-left: auto; }
.pgn-badges { display: flex; align-items: center; gap: var(--sp-8); }
.pgn-state {
  font-size: var(--fs-12); font-weight: 600; border-radius: var(--radius); white-space: nowrap;
  width: 48px; text-align: center;
}
.pgn-state.on { background: var(--ok-soft); color: var(--ok-text); border: 1px solid var(--ok-line); }
.pgn-state.off { background: var(--bg); color: var(--text-muted); border: 1px solid var(--border-strong); }
.engine-off-chip {
  font-size: var(--fs-12); font-weight: 600; padding: 0 var(--sp-8); border-radius: var(--radius); white-space: nowrap;
  background: var(--warn-soft); color: var(--warn-text); border: 1px solid var(--warn-line);
}
.details-btn { font-size: var(--fs-12); color: var(--accent); min-height: 24px !important; padding: 0 var(--sp-4); }
.pgn-details { background: var(--bg); border-bottom: 1px solid var(--border); }
.pgn-details-row {
  padding: var(--sp-4) var(--sp-12); border-bottom: 1px solid var(--border);
  display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: var(--sp-8);
}
.badge-subtle.badge-neutral { background: var(--bg); color: var(--text-muted); border-color: var(--border); }
.cycle-group { font-size: var(--fs-12); color: var(--text-muted); }
.cycle-group .unit { font-weight: 600; color: var(--text); }
.payload-strip {
  padding: var(--sp-4) var(--sp-12); background: var(--bg); color: var(--text-muted);
  display: flex; align-items: center; justify-content: space-between; font-size: var(--fs-12); flex-wrap: wrap; gap: var(--sp-8);
}
.payload-hex { font-weight: 600; color: var(--text); letter-spacing: 0.04em; }
/* Ignition: two-position switch, amber = key ON / engine off, green = engine running */
.ign-switch {
  display: inline-flex; border: 1px solid var(--border-strong); border-radius: var(--radius); overflow: hidden;
  background: var(--surface);
}
.ign-switch .ign-btn {
  font-size: var(--fs-13); font-weight: 600; padding: var(--sp-8) var(--sp-16); border-radius: 0;
  color: var(--text-muted) !important; background: var(--surface);
}
.ign-switch .ign-btn + .ign-btn { border-left: 1px solid var(--border-strong); }
.ign-switch .ign-btn.active-on { background: var(--warn) !important; color: var(--surface) !important; }
.ign-switch .ign-btn.active-run { background: var(--ok) !important; color: var(--surface) !important; }
.ign-note { font-size: var(--fs-12); color: var(--text-muted); padding: var(--sp-8) var(--sp-12); }

.signal-box { padding: var(--sp-4) var(--sp-12); }
/* Same column grid in every signal row so cards line up: SPN | name | value | controls */
.sig-row {
  display: grid; align-items: center; gap: var(--sp-4) var(--sp-12);
  grid-template-columns: 72px 196px 136px minmax(0, 1fr);
}
.sig-spn { display: flex; }
.signal-name { font-weight: 500; min-width: 0; line-height: 1.25; overflow-wrap: break-word; }
.spn-badge {
  font-size: var(--fs-12); font-weight: 500; background: var(--bg); color: var(--text-muted); white-space: nowrap;
  border: 1px solid var(--border); border-radius: var(--radius); padding: 0 var(--sp-4);
}
.sig-value {
  display: flex; align-items: baseline; justify-content: flex-end; gap: var(--sp-4); white-space: nowrap;
}
.sig-controls { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-4) var(--sp-8); min-width: 0; }
.signal-big {
  font-size: var(--fs-20); font-weight: 600; line-height: 1.1; color: var(--text);
  font-variant-numeric: tabular-nums;
}
.signal-unit { font-size: var(--fs-12); font-weight: 500; color: var(--text-muted); }
.signal-val { color: var(--text); }
.range-slider { flex: 1 1 80px; min-width: 80px; height: 24px; }
.compact-input .q-field__control,
.compact-input .q-field__marginal { height: 32px !important; min-height: 32px !important; }
.compact-input .q-field__native { padding: 0 !important; min-height: 32px !important; }
.value-input { width: 112px; flex-shrink: 0; }
.counter-input { width: 112px; flex-shrink: 0; }
.cycle-input { width: 80px; }
.preset-group { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-4); }
.preset-btn {
  font-size: var(--fs-12); padding: 0 var(--sp-8); min-height: 24px; border-radius: var(--radius);
  border: 1px solid var(--border-strong); background: var(--surface); color: var(--text);
  cursor: pointer; white-space: nowrap;
}
.step-group { display: flex; flex-wrap: wrap; gap: var(--sp-4); }
.step-btn {
  font-size: var(--fs-12); font-weight: 600; min-width: 48px; min-height: 28px; padding: 0 var(--sp-8);
  border-radius: var(--radius); border: 1px solid var(--border-strong); background: var(--surface);
  color: var(--text) !important; font-family: var(--font-mono) !important; font-variant-numeric: tabular-nums;
}
.sig-hint { font-size: var(--fs-16); color: var(--text-subtle); cursor: help; }

/* Traffic Monitor: dense table, newest frame at the bottom */
.traffic-card { display: flex; flex-direction: column; gap: var(--sp-8); }
.traffic-status {
  font-size: var(--fs-12); font-weight: 600; padding: 0 var(--sp-8); border-radius: var(--radius); white-space: nowrap;
}
.traffic-status.live { background: var(--ok-soft); color: var(--ok-text); border: 1px solid var(--ok-line); }
.traffic-status.paused { background: var(--warn-soft); color: var(--warn-text); border: 1px solid var(--warn-line); }
.traffic-box { position: relative; }
.traffic-filter { display: flex; align-items: center; gap: var(--sp-12); flex-wrap: wrap; font-size: var(--fs-12); }
.traffic-q {
  flex: 1 1 260px; min-width: 0; height: 32px; padding: 0 var(--sp-8); font-family: var(--font-mono);
  font-size: var(--fs-12); color: var(--text); background: var(--surface);
  border: 1px solid var(--border-strong); border-radius: var(--radius); outline: none;
}
.traffic-q:focus { border-color: var(--accent); box-shadow: var(--focus-ring); }
.traffic-chk { display: flex; align-items: center; gap: var(--sp-8); color: var(--text-muted); cursor: pointer; white-space: nowrap; }
.traffic-count { color: var(--text-muted); white-space: nowrap; margin-left: auto; }
.traffic-wrap {
  height: max(320px, calc(100vh - 380px)); overflow: auto;
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
}
.traffic-table {
  width: 100%; border-collapse: collapse; white-space: nowrap; font-size: var(--fs-12);
  font-family: var(--font-mono); font-variant-numeric: tabular-nums;
}
.traffic-table th {
  position: sticky; top: 0; z-index: 1; background: var(--bg); color: var(--text-muted); text-align: left;
  font-family: var(--font-ui); font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em;
  font-size: var(--fs-12); padding: var(--sp-4) var(--sp-8); border-bottom: 1px solid var(--border);
}
.traffic-table td { padding: 0 var(--sp-8); border-bottom: 1px solid var(--bg); color: var(--text); }
.traffic-table th:last-child, .traffic-table td:last-child { width: 100%; }
.traffic-table tr.tr-tx td:nth-child(2) { color: var(--accent); font-weight: 600; }
.traffic-table tr.tr-rx td:nth-child(2) { color: var(--ok-text); font-weight: 600; }
.traffic-table tr.tr-rx td { background: var(--ok-soft); }
.traffic-table tr.tr-err td { color: var(--danger-text); }
.traffic-table tr.tr-gap td { color: var(--text-subtle); font-style: italic; }
.traffic-table tr.tr-hidden { display: none; }
.traffic-table td:nth-child(9) { color: var(--accent); }
.traffic-table tr.tr-err td:nth-child(9) { color: var(--danger-text); }
.traffic-table tr.tr-gap td:nth-child(9) { color: var(--text-subtle); }
.traffic-empty { padding: var(--sp-16); color: var(--text-muted); font-size: var(--fs-12); }
.traffic-new {
  position: absolute; right: var(--sp-16); bottom: var(--sp-12); font-size: var(--fs-12); font-weight: 600;
  padding: var(--sp-4) var(--sp-12); border-radius: var(--radius); border: 1px solid var(--accent);
  background: var(--accent); color: var(--surface); cursor: pointer;
}

/* ECU & Vehicle */
.ecu-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(300px, 100%), 1fr)); gap: var(--sp-16); }
.truck-panel { padding: var(--sp-16); text-align: center; }
.truck-label { margin-top: var(--sp-8); font-size: var(--fs-12); font-weight: 600; color: var(--text); }
.addr-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--sp-8); font-size: var(--fs-12); }
.addr-cell {
  background: var(--surface); padding: var(--sp-8); border: 1px solid var(--border); border-radius: var(--radius);
}
.addr-label { color: var(--text-muted); font-size: var(--fs-12); display: block; }
.addr-value { font-weight: 600; }
.addr-name-hex { font-weight: 600; color: var(--text); }

.j1939-footer {
  min-height: 32px; background: var(--surface); border-top: 1px solid var(--border); padding: 0 var(--sp-16);
  display: flex; align-items: center; justify-content: space-between; font-size: var(--fs-12);
  color: var(--text-muted); flex-shrink: 0;
}
.footer-left, .footer-right { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-4) var(--sp-16); }
.footer-dtc { color: var(--ok-text); }
.footer-dtc.warn { color: var(--warn-text); }

/* Phones and narrow windows: nothing may push the page wider than the screen */
@media (max-width: 640px) {
  .topbar { padding: var(--sp-8) var(--sp-12); }
  .topbar-controls { width: 100%; justify-content: flex-start; }
  .j1939-main { padding: var(--sp-12) var(--sp-8); }
  .card { padding: var(--sp-12); }
  .bus-controls-group { width: 100%; }
  .bus-field, .bus-field-wide { flex: 1 1 100%; }
  .bus-select, .bus-field-wide .bus-select { width: 100%; }
  .run-stats { margin-left: 0; }
  .tab-bar { flex-wrap: wrap; }
  .tab-btn { padding: var(--sp-8) var(--sp-12); }
  .tab-pill { display: none; }
  .pgn-header .ign-switch { width: 100%; }
  .ign-switch .ign-btn { flex: 1 1 50%; padding: var(--sp-8); font-size: var(--fs-12); }
  .sig-row { grid-template-columns: auto minmax(0, 1fr) auto; }
  .sig-controls { grid-column: 1 / -1; }
  .range-slider { flex-basis: 100%; }
  .counter-input { flex: 1 1 100px; }
  .step-group { width: 100%; }
  .step-btn { flex: 1 1 0; min-width: 0; }
  .signal-big { font-size: var(--fs-16); }
  .j1939-footer { height: auto; padding: var(--sp-4) var(--sp-12); flex-wrap: wrap; gap: var(--sp-4) var(--sp-16); }
}
.stub-pane {
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: var(--sp-24);
  color: var(--text-muted); font-size: var(--fs-13);
}

/* Fault injection */
.pgn-toggle { cursor: pointer; user-select: none; }
.pgn-toggle:hover { filter: brightness(0.97); box-shadow: 0 0 0 1px var(--border-strong); }
.fault-chip {
  font-size: var(--fs-12); font-weight: 600; padding: 0 var(--sp-8); border-radius: var(--radius); white-space: nowrap;
  background: var(--danger-soft); color: var(--danger-text); border: 1px solid var(--danger-line);
}
.fault-summary { border-radius: var(--radius); padding: var(--sp-12); font-size: var(--fs-12); }
.fault-summary.ok { background: var(--ok-soft); color: var(--ok-text); border: 1px solid var(--ok-line); }
.fault-summary.active { background: var(--warn-soft); color: var(--warn-text); border: 1px solid var(--warn-line); }
.fault-summary-title { font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; font-size: var(--fs-12); }
.fault-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(min(340px, 100%), 1fr)); gap: var(--sp-12);
}
.fault-section {
  background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius); padding: var(--sp-12);
  display: flex; flex-direction: column; gap: var(--sp-8); min-width: 0;
}
.fault-section.fault-wide { grid-column: 1 / -1; }
.fault-title {
  font-weight: 600; font-size: var(--fs-12); text-transform: uppercase; letter-spacing: 0.04em; color: var(--text-muted);
}
.fault-text { font-size: var(--fs-12); color: var(--text-muted); line-height: 1.5; }
.fault-switch { font-size: var(--fs-12); font-weight: 600; color: var(--text); }
.fault-pgn-table {
  display: grid; grid-template-columns: auto auto auto minmax(0, 1fr) minmax(190px, 220px);
  align-items: center; gap: var(--sp-8) var(--sp-16); font-size: var(--fs-12);
}
.fault-cell-muted { color: var(--text-subtle); font-size: var(--fs-12); white-space: nowrap; }
.fault-cell-name { color: var(--text); min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fault-select { min-width: 190px; }
.footer-faults { color: var(--warn-text); font-weight: 600; }

/* Scenarios */
.footer-scenario { color: var(--accent); font-weight: 600; }
.scenario-banner {
  display: flex; align-items: center; gap: var(--sp-8); margin-bottom: var(--sp-8); padding: var(--sp-8) var(--sp-12);
  border-radius: var(--radius); font-size: var(--fs-12); background: var(--accent-soft); color: var(--accent);
  border: 1px solid var(--accent-line);
}
.scenario-upload { position: absolute; width: 1px; height: 1px; overflow: hidden; opacity: 0; pointer-events: none; }
.scenario-info {
  background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius); padding: var(--sp-12);
  display: flex; flex-direction: column; gap: var(--sp-4);
}
.scenario-title { font-weight: 600; font-size: var(--fs-13); color: var(--text); }
.scenario-desc { font-size: var(--fs-12); color: var(--text-muted); }
.scenario-meta { font-size: var(--fs-12); color: var(--text-muted); }
.scenario-dir { font-size: var(--fs-12); color: var(--text-subtle); word-break: break-all; margin-top: calc(-1 * var(--sp-8)); }
.scenario-error {
  background: var(--danger-soft); color: var(--danger-text); border: 1px solid var(--danger-line); border-radius: var(--radius);
  padding: var(--sp-8) var(--sp-12); font-size: var(--fs-12); white-space: pre-wrap;
}
.scenario-controls { display: flex; align-items: center; gap: var(--sp-8); flex-wrap: wrap; }
.scenario-state {
  font-size: var(--fs-12); font-weight: 600; padding: 0 var(--sp-8); border-radius: var(--radius); white-space: nowrap;
}
.scenario-state.idle, .scenario-state.stopped { background: var(--bg); color: var(--text-muted); border: 1px solid var(--border-strong); }
.scenario-state.running { background: var(--ok-soft); color: var(--ok-text); border: 1px solid var(--ok-line); }
.scenario-state.paused { background: var(--warn-soft); color: var(--warn-text); border: 1px solid var(--warn-line); }
.scenario-state.finished { background: var(--accent-soft); color: var(--accent); border: 1px solid var(--accent-line); }
.scenario-state.failed { background: var(--danger-soft); color: var(--danger-text); border: 1px solid var(--danger-line); white-space: normal; }
.scenario-clock { font-size: var(--fs-16); font-weight: 600; color: var(--text); font-variant-numeric: tabular-nums; }
.scenario-live { font-size: var(--fs-12); color: var(--text-muted); margin-left: auto; font-variant-numeric: tabular-nums; }
.scenario-steps {
  display: flex; flex-direction: column; border: 1px solid var(--border); border-radius: var(--radius);
  font-size: var(--fs-12); max-height: calc(100vh - 470px); min-height: 200px; overflow: auto;
}
.scenario-step {
  display: grid; grid-template-columns: 64px minmax(0, 1fr) auto; gap: var(--sp-12); align-items: start;
  padding: var(--sp-4) var(--sp-12); border-bottom: 1px solid var(--bg); color: var(--text); border-left: 3px solid transparent;
}
.scenario-step:last-child { border-bottom: none; }
.scenario-at { color: var(--text-muted); font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
.scenario-what { display: flex; flex-direction: column; min-width: 0; }
.scenario-note { color: var(--text-muted); font-style: italic; }
.scenario-eta { color: var(--accent); font-size: var(--fs-12); white-space: nowrap; font-family: var(--font-mono); }
.scenario-step.done { color: var(--text-subtle); }
.scenario-step.done .scenario-note, .scenario-step.done .scenario-at { color: var(--text-subtle); }
.scenario-step.current { background: var(--ok-soft); border-left-color: var(--ok); }
.scenario-step.next { background: var(--accent-soft); border-left-color: var(--accent-line); }
@media (max-width: 760px) {
  .fault-pgn-table { grid-template-columns: auto auto 1fr; }
  .fault-cell-name { grid-column: 1 / -1; }
  .fault-pgn-table .fault-select { grid-column: 1 / -1; }
}
"""
