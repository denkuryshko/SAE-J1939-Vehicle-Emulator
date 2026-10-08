"""Application CSS for the NiceGUI pages."""

APP_CSS = """
*, *::before, *::after { box-sizing: border-box; }
body, .nicegui-content {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
  background-color: #E8ECF0 !important;
  color: #1F2A37;
  font-size: 13px;
  line-height: 1.5;
}
.q-page, .nicegui-content { padding: 0 !important; }
.font-mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }

.j1939-root { width: 100%; min-height: 100vh; display: flex; flex-direction: column; background: #E8ECF0; }
.topbar {
  min-height: 48px; height: auto; background: #FFFFFF; border-bottom: 1px solid #CBD5E1;
  padding: 8px 16px; display: flex; flex-wrap: wrap; align-items: center;
  justify-content: space-between; gap: 8px 12px; flex-shrink: 0; row-gap: 8px;
}
.brand-section {
  display: flex; align-items: center; gap: 10px; min-width: 0; flex: 1 1 auto;
}
.brand-icon {
  width: 28px; height: 28px; background: #1F6FEB; color: white; border-radius: 3px;
  display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 14px;
  flex-shrink: 0;
}
.brand-title {
  font-weight: 800; font-size: 13px; letter-spacing: 0.04em; text-transform: uppercase;
  color: #1F2A37; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0;
}
.topbar-controls {
  display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px;
  flex: 0 1 auto; justify-content: flex-end;
}
@media (max-width: 900px) {
  .brand-title { max-width: 260px; }
}
@media (max-width: 640px) {
  .brand-title { display: none; }
}
.badge-subtle {
  font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 3px;
  background: #E7F0FD; color: #1F6FEB; border: 1px solid #B6D4FE;
}
.status-pill {
  display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: 3px;
  font-size: 11px; font-weight: 700; letter-spacing: 0.03em;
}
.status-pill.stopped { background: #F1F5F9; color: #64748B; border: 1px solid #CBD5E1; }
.status-pill.running { background: #EAF8F0; color: #1F9D55; border: 1px solid #A3E2BD; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.status-pill.stopped .status-dot { background: #94A3B8; }
.status-pill.running .status-dot { background: #1F9D55; }
.status-pill.warn { background: #FFFBEB; color: #B45309; border: 1px solid #FDE68A; }
.status-pill.warn .status-dot { background: #D97706; }
.status-pill.error { background: #FEF2F2; color: #B91C1C; border: 1px solid #FCA5A5; }
.status-pill.error .status-dot { background: #DC2626; }

/* Top-bar ECU state: the first thing to read on the bench */
.status-pill.status-hero {
  font-size: 13px; padding: 6px 14px; gap: 8px; border-width: 2px; border-radius: 4px;
}
.status-hero .status-dot { width: 11px; height: 11px; }
.status-hero.stopped { background: #F1F5F9; color: #475569; border-color: #94A3B8; }
.status-hero.running { background: #1F9D55; color: #FFFFFF; border-color: #1A8246; }
.status-hero.running .status-dot { background: #FFFFFF; animation: status-pulse 1.4s ease-in-out infinite; }
.status-hero.warn { background: #D97706; color: #FFFFFF; border-color: #B45309; }
.status-hero.warn .status-dot { background: #FFFFFF; }
.status-hero.error { background: #DC2626; color: #FFFFFF; border-color: #B91C1C; }
.status-hero.error .status-dot { background: #FFFFFF; }
@keyframes status-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }

.listen-group { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 6px; }
.host-input { width: 120px; }
.port-input { width: 90px; }

.j1939-main {
  flex: 1; max-width: 2200px; width: 100%; margin: 0 auto; padding: 14px;
  display: flex; flex-direction: column; gap: 12px;
}
/* Tabs on the left, the Logs panel always visible on the right (below them on narrow screens) */
.workspace {
  display: grid; grid-template-columns: minmax(0, 1fr) minmax(400px, 36%); gap: 12px;
  align-items: start;
}
.work-main { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
.work-logs { position: sticky; top: 12px; min-width: 0; }
.logs-panel {
  display: flex; flex-direction: column; gap: 16px;
  max-height: calc(100vh - 24px); overflow-y: auto;
}
.logs-live { font-size: 12px; font-weight: 700; color: #1F2A37; }
.logs-paused {
  font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: 3px;
  background: #FFFBEB; color: #B45309; border: 1px solid #FDE68A;
}
/* The trace fills the rest of the window height in the side panel */
.trace-log { height: max(320px, calc(100vh - 420px)); }
@media (max-width: 1100px) {
  .trace-log { height: 320px; }
  .workspace { grid-template-columns: minmax(0, 1fr); }
  .work-logs { position: static; }
  .logs-panel { max-height: none; }
}
.card {
  background: #FFFFFF; border: 1px solid #C5CCD6; border-radius: 3px;
  padding: 12px 14px; box-shadow: 0 1px 2px rgba(0,0,0,0.03);
}
.bus-bar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; }
.bus-controls-group { display: flex; flex-wrap: wrap; align-items: center; gap: 14px; }
.bus-field { flex: 0 1 auto; min-width: 0; }
.bus-select { width: 220px; max-width: 100%; }
.bus-field-wide .bus-select { width: 260px; }
.run-controls { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.run-stats {
  display: flex; flex-wrap: wrap; align-items: center; gap: 4px 12px;
  margin-left: 12px; font-size: 11px;
}
.vin-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 4px; }
.vin-input { flex: 1 1 210px; min-width: 0; font-weight: 700; text-transform: uppercase; }
.field-label {
  font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em;
  color: #5B6775; margin-bottom: 2px; display: block;
}
.action-btn {
  height: 30px; padding: 0 12px; font-size: 12px; font-weight: 700; border-radius: 3px;
  border: 1px solid transparent; cursor: pointer; display: inline-flex; align-items: center; gap: 6px;
}
.btn-start { background: #1F9D55; color: #FFFFFF; border-color: #1A8246; }
.btn-stop { background: #FFFFFF; color: #D32F2F; border-color: #C5CCD6; }
.btn-restart { background: #FFFFFF; color: #1F2A37; border-color: #C5CCD6; }
.btn-quit { background: #B91C1C; color: #FFFFFF; border-color: #991B1B; }
.btn-disabled { opacity: 0.5; pointer-events: none; }

.tab-bar {
  display: flex; background: #FFFFFF; border: 1px solid #C5CCD6; border-radius: 3px; overflow-x: auto;
}
.tab-btn {
  padding: 10px 16px; font-size: 12px; font-weight: 700; background: transparent; border: none;
  border-bottom: 2px solid transparent; color: #5B6775; cursor: pointer;
  display: inline-flex; align-items: center; gap: 8px; white-space: nowrap;
}
.tab-btn.active { color: #1F6FEB; border-bottom-color: #1F6FEB; background: #F4F8FD; }
.tab-pill {
  font-size: 10px; padding: 1px 5px; border-radius: 3px; background: #F1F5F9;
  color: #5B6775; border: 1px solid #CBD5E1; margin-left: 8px;
}
.tab-btn.active .tab-pill { background: #E7F0FD; color: #1F6FEB; border-color: #B6D4FE; }
.tab-pill.warn {
  background: #FFFBEB;
  color: #B45309;
  border-color: #FDE68A;
}

.dtc-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px;
}
.dtc-card {
  background: #FFFFFF;
  border: 1px solid #CBD5E1;
  border-radius: 3px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.dtc-card.fault-amber {
  background: #FFFBEB;
  border-color: #FBBF24;
  border-left: 4px solid #D97706;
}
.dtc-card.fault-red {
  background: #FEF2F2;
  border-color: #F87171;
  border-left: 4px solid #DC2626;
}

.pgn-header {
  padding: 10px 12px; background: #F8FAFC; border-bottom: 1px solid #CBD5E1;
  display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px;
}
.pgn-title-group { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.badge-acronym {
  font-size: 11px; font-weight: 800; background: #1F6FEB; color: #FFFFFF;
  padding: 2px 6px; border-radius: 3px;
}
.pgn-name { font-weight: 700; font-size: 13px; color: #1F2A37; }
.details-btn { font-size: 11px; color: #5B6775; }
.pgn-details { background: #FAFBFD; border-bottom: 1px solid #E2E8F0; }
.pgn-details-row {
  padding: 6px 12px; border-bottom: 1px solid #E2E8F0;
  display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px;
}
.payload-strip {
  padding: 6px 12px; background: #FAFBFD; border-bottom: 1px solid #E2E8F0;
  display: flex; align-items: center; justify-content: space-between; font-size: 11px; flex-wrap: wrap; gap: 6px;
}
/* Ignition: two-position switch, amber = key ON / engine off, green = engine running */
.ign-switch {
  display: inline-flex; border: 1px solid #C5CCD6; border-radius: 4px; overflow: hidden;
  background: #FFFFFF;
}
.ign-switch .ign-btn {
  font-size: 13px; font-weight: 700; padding: 6px 14px; border-radius: 0;
  color: #64748B !important; background: #FFFFFF;
}
.ign-switch .ign-btn + .ign-btn { border-left: 1px solid #C5CCD6; }
.ign-switch .ign-btn.active-on { background: #D97706 !important; color: #FFFFFF !important; }
.ign-switch .ign-btn.active-run { background: #1F9D55 !important; color: #FFFFFF !important; }

.signal-box { padding: 10px 12px; border-bottom: 1px solid #F1F5F9; }
.signal-top {
  display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center;
  gap: 4px 12px; margin-bottom: 6px;
}
.signal-title { display: flex; align-items: center; min-width: 0; }
.signal-readout { display: flex; align-items: baseline; gap: 4px; margin-left: auto; }
.signal-big { font-size: 18px; font-weight: 700; line-height: 1.1; color: #1F2A37; }
.signal-unit { font-size: 12px; font-weight: 600; color: #5B6775; }
.range-slider { flex: 1 1 auto; min-width: 0; }
.value-input { width: 110px; flex-shrink: 0; }
.preset-row {
  display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center;
  gap: 4px 8px; font-size: 10px; color: #5B6775;
}
.preset-group { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; }
.counter-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.counter-input { width: 170px; }
.step-group { display: flex; flex-wrap: wrap; gap: 4px; }
.step-btn {
  font-size: 12px; font-weight: 700; min-width: 56px; border-radius: 3px;
  border: 1px solid #CBD5E1; background: #FFFFFF; color: #1F2A37 !important;
}
.spn-badge {
  font-size: 10px; font-weight: 700; background: #F1F5F9; color: #475569;
  border: 1px solid #CBD5E1; border-radius: 3px; padding: 1px 5px; margin-right: 6px;
}
.signal-name { font-weight: 600; }
.signal-val { color: #1F2A37; }
.range-row { display: flex; align-items: center; gap: 10px; }
.preset-btn {
  font-size: 10px; padding: 2px 8px; border-radius: 3px; border: 1px solid #CBD5E1;
  background: #FFFFFF; color: #475569; cursor: pointer; font-family: inherit;
}

.j1939-footer {
  height: 26px; background: #E2E7ED; border-top: 1px solid #C5CCD6; padding: 0 14px;
  display: flex; align-items: center; justify-content: space-between; font-size: 11px;
  color: #5B6775; flex-shrink: 0;
}
.footer-left, .footer-right { display: flex; flex-wrap: wrap; align-items: center; gap: 2px 14px; }

/* Phones and narrow windows: nothing may push the page wider than the screen */
@media (max-width: 640px) {
  .topbar { padding: 8px 12px; }
  .topbar-controls { width: 100%; justify-content: flex-start; }
  .j1939-main { padding: 10px 8px; }
  .card { padding: 10px; }
  .bus-controls-group { width: 100%; }
  .bus-field, .bus-field-wide { flex: 1 1 100%; }
  .bus-select, .bus-field-wide .bus-select { width: 100%; }
  .run-stats { margin-left: 0; }
  .tab-bar { flex-wrap: wrap; }
  .tab-btn { padding: 8px 10px; }
  .tab-pill { display: none; }
  .pgn-header .ign-switch { width: 100%; }
  .ign-switch .ign-btn { flex: 1 1 50%; padding: 6px 8px; font-size: 12px; }
  .range-limit { display: none; }
  .value-input { width: 90px; }
  .counter-input { width: 100%; }
  .step-group { width: 100%; }
  .step-btn { flex: 1 1 0; min-width: 0; }
  .signal-big { font-size: 16px; }
  .j1939-footer { height: auto; padding: 4px 10px; flex-wrap: wrap; gap: 2px 14px; }
}
.stub-pane {
  background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 3px; padding: 24px;
  color: #5B6775; font-size: 13px;
}
"""
