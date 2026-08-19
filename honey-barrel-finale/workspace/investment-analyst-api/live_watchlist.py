import glob
import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

MAX_TRANSACTION_ROWS = 300


HTML_PAGE = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Live Watchlist Dashboard</title>
  <style>
    :root {
      --bg: #07090c;
      --bg-2: #0d1117;
      --bg-3: #11161d;
      --border: #1f2630;
      --text: #d7dde4;
      --muted: #6a7480;
      --amber: #ffb000;
      --cyan: #00bcd4;
      --green: #00ff7f;
      --red: #ff4d4d;
      --yellow: #ffd000;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: 'JetBrains Mono', ui-monospace, Menlo, monospace;
      background: var(--bg);
      color: var(--text);
      font-size: 13px;
    }
    .wrap { max-width: 1400px; margin: 20px auto; padding: 0 16px 32px; }
    .card {
      background: var(--bg-2);
      border: 1px solid var(--border);
      overflow: hidden;
      box-shadow: inset 0 0 0 1px rgba(255,255,255,0.01);
    }
    .head { padding: 14px 16px 12px; border-bottom: 1px solid var(--border); background: var(--bg-3); }
    .title { margin: 0; font-size: 18px; letter-spacing: 0.6px; color: var(--amber); text-transform: uppercase; }
    .meta { margin-top: 10px; display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 8px; font-size: 12px; color: var(--muted); }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 2px 8px;
      border: 1px solid var(--border);
      background: var(--bg);
      color: var(--text);
      font-size: 11px;
      letter-spacing: 0.4px;
      text-transform: uppercase;
      width: fit-content;
    }
    .controls { padding: 10px 16px; display: flex; flex-wrap: wrap; gap: 8px; border-bottom: 1px solid var(--border); background: rgba(255,255,255,0.02); }
    button.filter {
      border: 1px solid var(--border);
      background: var(--bg);
      color: var(--text);
      padding: 6px 10px;
      cursor: pointer;
      font-size: 11px;
      letter-spacing: 0.6px;
      text-transform: uppercase;
      transition: all 0.15s ease;
    }
    button.filter:hover { border-color: var(--amber); color: var(--amber); }
    button.filter.active { border-color: var(--amber); color: var(--amber); background: rgba(255, 176, 0, 0.08); }
    .table-wrap { overflow: auto; }
    table { width: 100%; border-collapse: collapse; min-width: 920px; }
    th, td { text-align: left; padding: 8px 12px; border-bottom: 1px solid #131820; font-size: 12px; vertical-align: top; }
    th { font-size: 10px; letter-spacing: 1px; color: var(--muted); text-transform: uppercase; }
    .sig { font-weight: 700; }
    .buy { color: var(--green); }
    .sell { color: var(--red); }
    .hold { color: var(--yellow); }
    a { color: var(--cyan); text-decoration: none; }
    a:hover { color: var(--amber); text-decoration: underline; }
    .foot { padding: 10px 16px 12px; color: var(--muted); font-size: 11px; }
    @media (max-width: 760px) { .title { font-size: 16px; } .meta { grid-template-columns: 1fr; } .controls { gap: 6px; } button.filter { padding: 6px 8px; font-size: 10px; } }
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"card\">
      <div class=\"head\">
        <h1 class=\"title\">Live Watchlist Dashboard</h1>
        <div class=\"meta\">
          <div id=\"market\"></div>
          <div id=\"clockLocal\"></div>
          <div id=\"clockNy\"></div>
          <div id=\"counts\"></div>
          <div id=\"source\"></div>
        </div>
      </div>

      <div class=\"controls\">
        <button class=\"filter active\" data-mode=\"all\">All</button>
        <button class=\"filter\" data-mode=\"buy_sell\">Buy/Sell</button>
        <button class=\"filter\" data-mode=\"buy\">Only Buy</button>
        <button class=\"filter\" data-mode=\"sell\">Only Sell</button>
        <button class=\"filter\" data-mode=\"hold\">Only Hold</button>
      </div>

      <div class=\"table-wrap\">
        <table>
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Signal</th>
              <th>Price</th>
              <th>Submitted At</th>
              <th>Status</th>
              <th>Order ID</th>
              <th>Report</th>
            </tr>
          </thead>
          <tbody id=\"tbody\"></tbody>
        </table>
      </div>

      <div class=\"foot\">Auto-refresh every 20s</div>
    </div>
  </div>

  <script>
    let mode = \"all\";
    const reportBasePath = \"/report\";

    function signalClass(signal) {
      if (signal === \"BUY\") return \"buy\";
      if (signal === \"SELL\") return \"sell\";
      if (signal === \"HOLD\") return \"hold\";
      return \"\";
    }

    function fmtText(label, value) {
      return `${label}: ${value}`;
    }

    function fmtPrice(value) {
      const n = Number(value);
      if (!Number.isFinite(n) || n <= 0) return "-";
      return n.toFixed(4);
    }

    async function load() {
      const res = await fetch(`/api/snapshot?mode=${encodeURIComponent(mode)}`);
      if (!res.ok) return;
      const data = await res.json();

      document.getElementById("market").innerHTML = `<span class="pill">${data.market_status}</span>`;
      document.getElementById("clockLocal").textContent = fmtText("LOCAL", data.local_time);
      document.getElementById("clockNy").textContent = fmtText("NY", data.ny_time);
      document.getElementById("counts").textContent = `TICKERS ${data.total_tickers} | BUY ${data.counts.BUY} | SELL ${data.counts.SELL} | HOLD ${data.counts.HOLD} | NO_DATA ${data.counts.NO_DATA}`;
      document.getElementById("source").textContent = fmtText("SOURCE", data.source);

      const tbody = document.getElementById(\"tbody\");
      tbody.innerHTML = \"\";
      for (const row of data.rows) {
        const tr = document.createElement(\"tr\");
        tr.innerHTML = `
          <td>${row.ticker}</td>
          <td class=\"sig ${signalClass(row.signal)}\">${row.signal}</td>
          <td>${fmtPrice(row.price)}</td>
          <td>${row.submitted_at || \"-\"}</td>
          <td>${row.status || \"-\"}</td>
          <td class=\"muted\" style=\"font-size:10px;word-break:break-all\">${row.order_id || \"-\"}</td>
          <td>${row.report_link ? `<a href=\"${row.report_link}\" target=\"_blank\" rel=\"noopener\">open</a>` : \"-\"}</td>
        `;
        tbody.appendChild(tr);
      }
    }

    for (const btn of document.querySelectorAll(\"button.filter\")) {
      btn.addEventListener(\"click\", () => {
        mode = btn.dataset.mode;
        document.querySelectorAll(\"button.filter\").forEach((b) => b.classList.remove(\"active\"));
        btn.classList.add(\"active\");
        load();
      });
    }

    load();
    setInterval(load, 20000);
  </script>
</body>
</html>
"""


def build_html_page() -> str:
    return HTML_PAGE


def parse_tickers(cron_snapshot_file: str):
    if not os.path.isfile(cron_snapshot_file):
        return []
    with open(cron_snapshot_file, encoding="utf-8", errors="ignore") as handle:
        content = handle.read()
    tickers = []
    for match in re.finditer(r"WATCHLIST_TICKERS='([^']+)'", content):
        raw_symbols = match.group(1).strip().upper()
        for symbol in raw_symbols.split(","):
            symbol = symbol.strip()
            if symbol and symbol not in tickers:
                tickers.append(symbol)
    return tickers


def resolve_signal(doc: dict):
    status = str(doc.get("order_status") or doc.get("status") or "").upper().strip()
    side = str(doc.get("side") or doc.get("order_side") or doc.get("action") or "").upper().strip()
    action = side if side in {"BUY", "SELL", "HOLD"} else str(doc.get("action") or doc.get("order_status") or "").upper().strip()

    if action not in {"BUY", "SELL", "HOLD"}:
        if status in {"BUY", "SELL", "HOLD"}:
            action = status
        elif side in {"BUY", "SELL", "HOLD"}:
            action = side
        elif status == "ACCEPTED":
            action = side or "TRADE"
        else:
            action = action or status or "UNKNOWN"

    return action, status or "unknown"


def resolve_trade_price(doc: dict):
    for key in ("execution_price", "avg_price", "filled_avg_price", "limit_price", "current_price", "price", "avg_fill_price"):
        value = doc.get(key)
        if value is None or value == "":
            continue
        try:
            price = float(value)
        except (TypeError, ValueError):
            continue
        if price > 0:
            return price
    return None


def _parse_submitted_at(value: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        return datetime.min.replace(tzinfo=timezone.utc)

    candidates = [text]
    if text.endswith("Z"):
        candidates.append(text[:-1] + "+00:00")

    for raw in candidates:
        try:
            parsed = datetime.fromisoformat(raw)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except Exception:
            continue

    return datetime.min.replace(tzinfo=timezone.utc)


def _record_is_newer(candidate: dict, existing: dict) -> bool:
    candidate_ts = _parse_submitted_at(candidate.get("submitted_at"))
    existing_ts = _parse_submitted_at(existing.get("submitted_at"))
    if candidate_ts != existing_ts:
        return candidate_ts > existing_ts
    return str(candidate.get("submitted_at") or "") > str(existing.get("submitted_at") or "")


def _normalize_history_record(doc: dict, source_path: str):
    symbol = str(doc.get("symbol") or doc.get("ticker") or "").upper().strip()
    if not symbol:
        return None

    signal, status = resolve_signal(doc)
    return {
        "ticker": symbol,
        "signal": signal,
        "status": status,
        "price": resolve_trade_price(doc),
        "submitted_at": str(doc.get("submitted_at") or doc.get("created_at") or doc.get("updated_at") or doc.get("timestamp") or ""),
        "report_file": source_path,
    }


def read_historical_order_records(reports_dir: str):
    history_path = os.path.join(reports_dir, "alpaca_orders_history.jsonl")
    if not os.path.isfile(history_path):
        return []

    records = []
    try:
        with open(history_path, encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    data = json.loads(stripped)
                except Exception:
                    continue
                record = _normalize_history_record(data, history_path)
                if record is not None:
                    records.append(record)
    except Exception:
        return []
    return records


def fetch_alpaca_live_orders(alpaca_mcp_url: str, limit: int = 100) -> list[dict]:
    """Fetch recent orders from the Alpaca MCP service and normalise them into
    the same record shape used by the rest of build_snapshot."""
    if not alpaca_mcp_url:
        return []
    try:
        payload = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "orders_list", "arguments": {"status": "all", "limit": limit}},
        }).encode()
        req = urllib.request.Request(
            f"{alpaca_mcp_url.rstrip('/')}/mcp",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            rpc = json.loads(resp.read())

        content = ((rpc.get("result") or {}).get("content") or [])
        raw_orders = None
        for item in content:
            if item.get("type") == "text" and item.get("text"):
                raw_orders = json.loads(item["text"])
                break
        if raw_orders is None or rpc.get("error"):
            return []
    except Exception:
        return []

    records = []
    if isinstance(raw_orders, dict):
        raw_orders = [raw_orders]
    if not isinstance(raw_orders, list):
        return []

    for order in raw_orders:
        symbol = str(order.get("symbol") or "").upper().strip()
        if not symbol:
            continue
        side = str(order.get("side") or "").upper().strip()
        status = str(order.get("status") or "").upper().strip()
        # Map Alpaca side (buy/sell) → signal
        if side in {"BUY", "SELL"}:
            signal = side
        elif status in {"BUY", "SELL"}:
            signal = status
        else:
            # Skip non-directional orders (e.g. cancelled without side info)
            continue

        price = None
        for key in ("filled_avg_price", "limit_price", "notional"):
            val = order.get(key)
            if val is not None and val != "" and val != "0":
                try:
                    f = float(val)
                    if f > 0:
                        price = f
                        break
                except (TypeError, ValueError):
                    pass

        submitted_at = str(
            order.get("submitted_at") or order.get("created_at") or order.get("updated_at") or ""
        )
        records.append({
            "ticker": symbol,
            "signal": signal,
            "status": status.lower() if status else "unknown",
            "price": price,
            "submitted_at": submitted_at,
            "report_file": "",
            "order_id": str(order.get("id") or ""),
            "_source": "alpaca_live",
        })
    return records


def build_snapshot(cron_snapshot_file: str, reports_dir: str, mode: str, workspace_root: str, alpaca_mcp_url: str = ""):
    tickers = parse_tickers(cron_snapshot_file)
    report_pattern = os.path.join(reports_dir, "investment_analysis_cycle_*.json")
    report_files = sorted(glob.glob(report_pattern), key=os.path.getmtime, reverse=True)

    latest = {}
    transaction_candidates: list[dict] = []
    for path in report_files:
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception:
            continue

        symbol = str(data.get("symbol") or "").upper().strip()
        if not symbol:
            continue

        signal, status = resolve_signal(data)
        record = {
            "ticker": symbol,
            "signal": signal,
            "status": status,
            "price": resolve_trade_price(data),
            "submitted_at": str(data.get("submitted_at") or ""),
            "report_file": os.path.relpath(path, start=workspace_root),
        }
        if signal in {"BUY", "SELL"}:
            transaction_candidates.append(record)

        if symbol not in latest:
            latest[symbol] = record
        elif symbol in tickers and _record_is_newer(record, latest[symbol]):
            latest[symbol] = record

    for record in read_historical_order_records(reports_dir):
        record["report_file"] = os.path.relpath(record["report_file"], start=workspace_root)
        if record["signal"] in {"BUY", "SELL"}:
            transaction_candidates.append(record)
        symbol = record["ticker"]
        if symbol not in latest:
            latest[symbol] = record
        elif _record_is_newer(record, latest[symbol]):
            latest[symbol] = record

    # Merge real Alpaca orders fetched live from the MCP service.
    # These take precedence over stale file-based records for the same symbol.
    for live_record in fetch_alpaca_live_orders(alpaca_mcp_url):
        signal = live_record["signal"]
        if signal in {"BUY", "SELL"}:
            transaction_candidates.append(live_record)
        symbol = live_record["ticker"]
        if symbol not in latest or _record_is_newer(live_record, latest[symbol]):
            latest[symbol] = live_record

    seen_transactions = set()
    transaction_rows = []
    for record in sorted(
        transaction_candidates,
        key=lambda row: (_parse_submitted_at(row.get("submitted_at")), str(row.get("ticker") or "")),
        reverse=True,
    ):
        signal = str(record.get("signal") or "").upper().strip()
        if signal not in {"BUY", "SELL"}:
            continue
        key = (
            str(record.get("ticker") or "").upper().strip(),
            signal,
            str(record.get("status") or "").upper().strip(),
            str(record.get("submitted_at") or "").strip(),
            round(float(record.get("price")), 8) if isinstance(record.get("price"), (int, float)) else None,
        )
        if key in seen_transactions:
            continue
        seen_transactions.add(key)

        report_path = str(record.get("report_file") or "").replace("\\", "/")
        transaction_rows.append(
            {
                "ticker": record.get("ticker"),
                "signal": signal,
                "price": record.get("price"),
                "status": record.get("status"),
                "submitted_at": record.get("submitted_at"),
                "order_id": record.get("order_id") or "",
                "report_link": f"/report?path={quote(report_path)}" if report_path else "",
            }
        )
        if len(transaction_rows) >= MAX_TRANSACTION_ROWS:
            break

    ordered_symbols = sorted(
        set(tickers) | set(latest.keys()),
        key=lambda symbol: (
            {"BUY": 0, "SELL": 1, "HOLD": 2}.get(latest.get(symbol, {}).get("signal"), 3),
            symbol,
        ),
    )

    now_local = datetime.now().astimezone()
    now_ny = datetime.now(ZoneInfo("America/New_York"))
    is_weekday = now_ny.weekday() < 5
    mins = now_ny.hour * 60 + now_ny.minute
    market_open = is_weekday and (9 * 60 + 30) <= mins < (16 * 60)

    counts = {"BUY": 0, "SELL": 0, "HOLD": 0, "OTHER": 0, "NO_DATA": 0}
    for symbol in ordered_symbols:
        row = latest.get(symbol)
        if not row:
            if symbol in tickers:
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
    if mode in {"buy", "sell", "buy_sell"}:
        rows.extend([row for row in transaction_rows if allow(row["signal"])])
    elif mode == "hold":
        for symbol in ordered_symbols:
            row = latest.get(symbol)
            if not row:
                continue
            if not allow(row["signal"]):
                continue
            report_path = row["report_file"].replace("\\", "/")
            rows.append(
                {
                    "ticker": row["ticker"],
                    "signal": row["signal"],
                    "price": row.get("price"),
                    "status": row["status"],
                    "submitted_at": row["submitted_at"],
                    "order_id": row.get("order_id") or "",
                    "report_link": f"/report?path={quote(report_path)}" if report_path else "",
                }
            )
    else:
        rows.extend(transaction_rows)
        for symbol in ordered_symbols:
            row = latest.get(symbol)
            if not row:
                if symbol in tickers:
                    rows.append(
                        {
                            "ticker": symbol,
                            "signal": "NO_DATA",
                            "price": None,
                            "status": "-",
                            "submitted_at": "",
                            "order_id": "",
                            "report_link": "",
                        }
                    )
                continue
            if row["signal"] in {"BUY", "SELL"}:
                continue
            report_path = row["report_file"].replace("\\", "/")
            rows.append(
                {
                    "ticker": row["ticker"],
                    "signal": row["signal"],
                    "price": row.get("price"),
                    "status": row["status"],
                    "submitted_at": row["submitted_at"],
                    "order_id": row.get("order_id") or "",
                    "report_link": f"/report?path={quote(report_path)}" if report_path else "",
                }
            )

    return {
        "market_status": "OPEN" if market_open else "CLOSED",
        "local_time": now_local.strftime("%Y-%m-%d %H:%M:%S %Z (%z)"),
        "ny_time": now_ny.strftime("%Y-%m-%d %H:%M:%S %Z (%z)"),
        "source": os.path.relpath(cron_snapshot_file, start=workspace_root),
        "total_tickers": len(ordered_symbols),
        "counts": counts,
        "mode": mode,
        "rows": rows,
    }
