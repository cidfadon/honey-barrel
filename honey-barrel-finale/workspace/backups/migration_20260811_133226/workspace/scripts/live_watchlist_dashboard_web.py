#!/usr/bin/env python3
import argparse
import glob
import json
import os
import re
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse
from zoneinfo import ZoneInfo


HTML_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Live Watchlist Dashboard</title>
  <style>
    :root {
      --bg: #f4f1ea;
      --panel: #fffdf9;
      --ink: #1f2a2e;
      --muted: #617278;
      --line: #d8d0c2;
      --buy: #0d7a3f;
      --sell: #a22d2d;
      --hold: #9a6a00;
      --accent: #0f5d84;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      background: radial-gradient(1200px 500px at 20% -10%, #e9efe6, transparent),
                  radial-gradient(900px 500px at 120% 0%, #e4edf3, transparent),
                  var(--bg);
      color: var(--ink);
    }
    .wrap {
      max-width: 1200px;
      margin: 24px auto;
      padding: 0 16px 40px;
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 16px;
      box-shadow: 0 10px 30px rgba(31, 42, 46, 0.08);
      overflow: hidden;
    }
    .head {
      padding: 18px 18px 10px;
      border-bottom: 1px solid var(--line);
    }
    .title {
      margin: 0;
      font-size: 24px;
      letter-spacing: 0.2px;
    }
    .meta {
      margin-top: 10px;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 10px;
      font-size: 13px;
      color: var(--muted);
    }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border-radius: 999px;
      padding: 4px 10px;
      background: #eef3f5;
      color: var(--accent);
      font-weight: 600;
      width: fit-content;
    }
    .controls {
      padding: 12px 18px;
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      border-bottom: 1px solid var(--line);
    }
    button.filter {
      border: 1px solid var(--line);
      background: #fff;
      color: var(--ink);
      padding: 8px 12px;
      border-radius: 10px;
      cursor: pointer;
      font-weight: 600;
      transition: all 0.15s ease;
    }
    button.filter:hover { transform: translateY(-1px); }
    button.filter.active {
      border-color: var(--accent);
      color: #fff;
      background: var(--accent);
    }
    .table-wrap { overflow: auto; }
    table {
      width: 100%;
      border-collapse: collapse;
      min-width: 920px;
    }
    th, td {
      text-align: left;
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      font-size: 14px;
      vertical-align: top;
    }
    th { font-size: 12px; letter-spacing: 0.4px; color: var(--muted); text-transform: uppercase; }
    .sig { font-weight: 700; }
    .buy { color: var(--buy); }
    .sell { color: var(--sell); }
    .hold { color: var(--hold); }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }
    .foot {
      padding: 12px 18px 16px;
      color: var(--muted);
      font-size: 12px;
    }
    @media (max-width: 760px) {
      .title { font-size: 20px; }
      .meta { grid-template-columns: 1fr; }
      .controls { gap: 6px; }
      button.filter { padding: 7px 10px; font-size: 13px; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <div class="head">
        <h1 class="title">Live Watchlist Dashboard</h1>
        <div class="meta">
          <div id="market"></div>
          <div id="clockLocal"></div>
          <div id="clockNy"></div>
          <div id="counts"></div>
          <div id="source"></div>
        </div>
      </div>

      <div class="controls">
        <button class="filter active" data-mode="all">All</button>
        <button class="filter" data-mode="buy_sell">Buy/Sell</button>
        <button class="filter" data-mode="buy">Only Buy</button>
        <button class="filter" data-mode="sell">Only Sell</button>
        <button class="filter" data-mode="hold">Only Hold</button>
      </div>

      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Signal</th>
              <th>Price</th>
              <th>Qty</th>
              <th>Submitted At</th>
              <th>Status</th>
              <th>Report</th>
            </tr>
          </thead>
          <tbody id="tbody"></tbody>
        </table>
      </div>

      <div class="foot">Auto-refresh every 20s</div>
    </div>
  </div>

  <script>
    let mode = "all";

    function signalClass(signal) {
      if (signal === "BUY") return "buy";
      if (signal === "SELL") return "sell";
      if (signal === "HOLD") return "hold";
      return "";
    }

    function fmtText(label, value) {
      return `${label}: ${value}`;
    }

    function fmtPrice(value) {
      const n = Number(value);
      if (!Number.isFinite(n) || n <= 0) return "-";
      return n.toFixed(4);
    }

    function fmtQty(value) {
      const n = Number(value);
      if (!Number.isFinite(n) || n <= 0) return "-";
      return n.toFixed(4).replace(/\\.0+$/, "").replace(/(\\.\\d*?)0+$/, "$1");
    }

    async function load() {
      const res = await fetch(`/api/snapshot?mode=${encodeURIComponent(mode)}`);
      if (!res.ok) return;
      const data = await res.json();

      document.getElementById("market").innerHTML = `<span class="pill">Market ${data.market_status}</span>`;
      document.getElementById("clockLocal").textContent = fmtText("Local", data.local_time);
      document.getElementById("clockNy").textContent = fmtText("NY", data.ny_time);
      document.getElementById("counts").textContent = `Tickers ${data.total_tickers} | BUY ${data.counts.BUY} | SELL ${data.counts.SELL} | HOLD ${data.counts.HOLD} | NO_DATA ${data.counts.NO_DATA}`;
      document.getElementById("source").textContent = fmtText("Source", data.source);

      const tbody = document.getElementById("tbody");
      tbody.innerHTML = "";
      for (const row of data.rows) {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${row.ticker}</td>
          <td class="sig ${signalClass(row.signal)}">${row.signal}</td>
          <td>${fmtPrice(row.price)}</td>
          <td>${fmtQty(row.qty)}</td>
          <td>${row.submitted_at || "-"}</td>
          <td>${row.status || "-"}</td>
          <td>${row.report_link ? `<a href="${row.report_link}" target="_blank" rel="noopener">open</a>` : "-"}</td>
        `;
        tbody.appendChild(tr);
      }
    }

    for (const btn of document.querySelectorAll("button.filter")) {
      btn.addEventListener("click", () => {
        mode = btn.dataset.mode;
        document.querySelectorAll("button.filter").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        load();
      });
    }

    load();
    setInterval(load, 20000);
  </script>
</body>
</html>
"""


def parse_tickers(cron_snapshot_file: str):
  if not os.path.isfile(cron_snapshot_file):
    return []
  with open(cron_snapshot_file, encoding="utf-8", errors="ignore") as handle:
    content = handle.read()
  tickers = []
  for match in re.finditer(r"WATCHLIST_TICKERS='([^']+)'", content):
    symbol = match.group(1).strip().upper()
    if symbol and symbol not in tickers:
      tickers.append(symbol)
  return tickers


def resolve_signal(doc: dict):
  action = str(doc.get("action") or doc.get("order_status") or "").upper().strip()
  status = str(doc.get("order_status") or "").upper().strip()

  if action not in {"BUY", "SELL", "HOLD"}:
    if status in {"BUY", "SELL", "HOLD"}:
      action = status
    elif status == "ACCEPTED":
      side = str(doc.get("action") or "").upper().strip() or "TRADE"
      action = side
    else:
      action = action or status or "UNKNOWN"

  return action, status or "unknown"


def build_snapshot(cron_snapshot_file: str, reports_dir: str, mode: str, workspace_root: str):
  tickers = parse_tickers(cron_snapshot_file)
  report_pattern = os.path.join(reports_dir, "investment_analysis_cycle_*.json")
  report_files = sorted(glob.glob(report_pattern), key=os.path.getmtime, reverse=True)

  latest = {}
  for path in report_files:
    try:
      with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    except Exception:
      continue

    symbol = str(data.get("symbol") or "").upper().strip()
    if not symbol or symbol not in tickers or symbol in latest:
      continue

    signal, status = resolve_signal(data)
    latest[symbol] = {
      "ticker": symbol,
      "signal": signal,
      "status": status,
      "price": data.get("current_price"),
      "qty": data.get("final_qty"),
      "submitted_at": str(data.get("submitted_at") or ""),
      "report_file": os.path.relpath(path, start=workspace_root),
    }
    if len(latest) == len(tickers):
      break

  now_local = datetime.now().astimezone()
  now_ny = datetime.now(ZoneInfo("America/New_York"))
  is_weekday = now_ny.weekday() < 5
  mins = now_ny.hour * 60 + now_ny.minute
  market_open = is_weekday and (9 * 60 + 30) <= mins < (16 * 60)

  counts = {"BUY": 0, "SELL": 0, "HOLD": 0, "OTHER": 0, "NO_DATA": 0}
  for ticker in tickers:
    row = latest.get(ticker)
    if not row:
      counts["NO_DATA"] += 1
      continue
    signal = row["signal"]
    if signal in counts:
      counts[signal] += 1
    else:
      counts["OTHER"] += 1

  def allow(row_signal: str):
    if mode == "buy":
      return row_signal == "BUY"
    if mode == "sell":
      return row_signal == "SELL"
    if mode == "hold":
      return row_signal == "HOLD"
    if mode == "buy_sell":
      return row_signal in {"BUY", "SELL"}
    return True

  def sort_key(ticker: str):
    row = latest.get(ticker)
    if not row:
      return (4, ticker)
    priority = {"BUY": 0, "SELL": 1, "HOLD": 2}.get(row["signal"], 3)
    return (priority, ticker)

  rows = []
  for ticker in sorted(tickers, key=sort_key):
    row = latest.get(ticker)
    if not row:
      if mode == "all":
        rows.append(
          {
            "ticker": ticker,
            "signal": "NO_DATA",
            "price": None,
            "qty": None,
            "status": "-",
            "submitted_at": "",
            "report_link": "",
          }
        )
      continue

    if not allow(row["signal"]):
      continue

    report_path = row["report_file"].replace("\\", "/")
    rows.append(
      {
        "ticker": row["ticker"],
        "signal": row["signal"],
        "price": row.get("price"),
        "qty": row.get("qty"),
        "status": row["status"],
        "submitted_at": row["submitted_at"],
        "report_link": f"/report?path={quote(report_path)}",
      }
    )

  return {
    "market_status": "OPEN" if market_open else "CLOSED",
    "local_time": now_local.strftime("%Y-%m-%d %H:%M:%S %Z (%z)"),
    "ny_time": now_ny.strftime("%Y-%m-%d %H:%M:%S %Z (%z)"),
    "source": os.path.relpath(cron_snapshot_file, start=workspace_root),
    "total_tickers": len(tickers),
    "counts": counts,
    "mode": mode,
    "rows": rows,
  }


class DashboardHandler(BaseHTTPRequestHandler):
  cron_snapshot_file = ""
  reports_dir = ""
  workspace_root = ""
  lock = threading.Lock()

  def _send(self, status: int, body: bytes, content_type: str):
    self.send_response(status)
    self.send_header("Content-Type", content_type)
    self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
    self.send_header("Access-Control-Allow-Origin", "*")
    self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
    self.send_header("Access-Control-Allow-Headers", "Content-Type")
    self.end_headers()
    self.wfile.write(body)

  def do_OPTIONS(self):
    self.send_response(204)
    self.send_header("Access-Control-Allow-Origin", "*")
    self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
    self.send_header("Access-Control-Allow-Headers", "Content-Type")
    self.end_headers()

  def do_GET(self):
    parsed = urlparse(self.path)
    if parsed.path == "/":
      self._send(200, HTML_PAGE.encode("utf-8"), "text/html; charset=utf-8")
      return

    if parsed.path == "/api/snapshot":
      query = parse_qs(parsed.query)
      mode = (query.get("mode", ["all"])[0] or "all").strip().lower()
      if mode not in {"all", "buy", "sell", "hold", "buy_sell"}:
        mode = "all"
      with self.lock:
        payload = build_snapshot(self.cron_snapshot_file, self.reports_dir, mode, self.workspace_root)
      self._send(200, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")
      return

    if parsed.path == "/report":
      query = parse_qs(parsed.query)
      rel_path = unquote((query.get("path", [""])[0] or "").strip())
      rel_path = rel_path.replace("\\", "/")
      if not rel_path.startswith("reports/"):
        self._send(400, b"invalid report path", "text/plain; charset=utf-8")
        return

      abs_path = os.path.abspath(os.path.join(self.workspace_root, rel_path))
      workspace_root_abs = os.path.abspath(self.workspace_root)
      if not abs_path.startswith(workspace_root_abs + os.sep):
        self._send(400, b"invalid report path", "text/plain; charset=utf-8")
        return
      if not os.path.isfile(abs_path):
        self._send(404, b"report not found", "text/plain; charset=utf-8")
        return

      with open(abs_path, "rb") as report_file:
        raw = report_file.read()

      if abs_path.endswith(".json"):
        ctype = "application/json; charset=utf-8"
      elif abs_path.endswith(".md"):
        ctype = "text/markdown; charset=utf-8"
      else:
        ctype = "text/plain; charset=utf-8"
      self._send(200, raw, ctype)
      return

    self._send(404, b"not found", "text/plain; charset=utf-8")

  def log_message(self, fmt, *args):
    return


def main():
  parser = argparse.ArgumentParser(description="Live watchlist web dashboard with filter buttons.")
  parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
  parser.add_argument("--port", type=int, default=8787, help="Bind port (default: 8787)")
  parser.add_argument(
    "--cron-snapshot",
    default="reports/.cron_state/crontab_mbednarski.txt",
    help="Path to crontab snapshot file (default: reports/.cron_state/crontab_mbednarski.txt)",
  )
  parser.add_argument(
    "--reports-dir",
    default="reports",
    help="Path to reports directory (default: reports)",
  )
  args = parser.parse_args()

  script_dir = os.path.dirname(os.path.abspath(__file__))
  workspace_root = os.path.abspath(os.path.join(script_dir, ".."))

  if os.path.isabs(args.cron_snapshot):
    cron_snapshot_file = args.cron_snapshot
  else:
    cron_snapshot_file = os.path.abspath(os.path.join(workspace_root, args.cron_snapshot))

  if os.path.isabs(args.reports_dir):
    reports_dir = args.reports_dir
  else:
    reports_dir = os.path.abspath(os.path.join(workspace_root, args.reports_dir))

  DashboardHandler.cron_snapshot_file = cron_snapshot_file
  DashboardHandler.reports_dir = reports_dir
  DashboardHandler.workspace_root = workspace_root

  server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
  print(f"Live dashboard running on http://{args.host}:{args.port}")
  print("Press Ctrl+C to stop.")
  try:
    server.serve_forever()
  except KeyboardInterrupt:
    pass
  finally:
    server.server_close()


if __name__ == "__main__":
  main()
