"""Investment Analyst API - FastAPI application."""
import math
import os
import socket
import time
import threading
import subprocess
import shutil
import uuid
import shlex
import difflib
import html
import re
import statistics
from datetime import datetime, time as dt_time, timezone
from pathlib import Path
from typing import Any, List, Optional
import requests
import json
from urllib.parse import quote, unquote, parse_qs, urlparse

from fastapi import FastAPI, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from prometheus_fastapi_instrumentator import Instrumentator

from config import DEMO_MODE, MODEL_ALGORITHM
from data_fetcher import DataFetcher
from mcp import attach_mcp
from ml_model import StockPredictor
from watchlist import WatchListManager
from live_watchlist import build_html_page, build_snapshot

APP_VERSION = os.getenv("UI_VERSION", "v0.1.2 (BETA)").strip() or "v0.1.2 (BETA)"

app = FastAPI(
    title="Investment Analyst API",
    description="Stock analysis with ML predictions",
    version=APP_VERSION,
)

Instrumentator().instrument(app).expose(app, endpoint="/api/metrics")


@app.middleware("http")
async def no_cache_ui_responses(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/ui"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Initialize services
data_fetcher = DataFetcher()
predictor = StockPredictor(algorithm=MODEL_ALGORITHM)
watchlist_mgr = WatchListManager()

# Mount the MCP server (GET /mcp SSE + POST /mcp JSON-RPC 2.0).
# Same shape as mcp-toolbox / workspace-mcp / alpaca-mcp so Hermes registers
# it via `hermes mcp add analyst --url http://investment-analyst-api:8001/mcp`.
attach_mcp(
    app,
    data_fetcher=data_fetcher,
    predictor=predictor,
    watchlist_mgr=watchlist_mgr,
)

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_STATIC_DIR):
    app.mount("/ui", StaticFiles(directory=_STATIC_DIR, html=True), name="ui")

_WORKSPACE_ROOT = Path(os.getenv("WORKSPACE_DIR", "/workspace")).resolve()
_DOCS_DIR = (_WORKSPACE_ROOT / "docs").resolve()
_REPORTS_DIR = Path(os.getenv("REPORTS_DIR", "/workspace/reports")).resolve()
_WATCHLIST_RUNNER_SCRIPT = (_WORKSPACE_ROOT / "scripts" / "daily_investment_watchlist_report_generator.sh").resolve()
_LIVE_WATCHLIST_URL = os.getenv("LIVE_WATCHLIST_URL", "/live-watchlist").strip() or "/live-watchlist"
_NASDAQ_SYMBOLS_FILE = _DOCS_DIR / "NASDAQ_SYMBOLS.md"
_NASDAQ_MIDCAP_FILE = _DOCS_DIR / "NASDAQ_midCap.md"
_NASDAQ_SMALLCAP_FILE = _DOCS_DIR / "NASDAQ_smallCap.md"
_CORE_STACK_CONTAINERS = [
    "investment-analyst-api",
    "alpaca-mcp",
    "workspace-mcp",
    "mcp-toolbox",
    "hermes",
    "stdio-terminal",
    "workspace",
]
_MONITORING_STACK_CONTAINERS = [
    "prometheus",
    "grafana",
    "node-exporter",
    "cadvisor",
    "hermes-exporter",
    "ollama-exporter",
    "alpaca-exporter",
]
_DOCKER_JOB_LOCK = threading.Lock()
_DOCKER_JOBS: dict[str, dict[str, Any]] = {}
_DOCKER_JOBS_STATE_FILE = (_WORKSPACE_ROOT / "reports" / ".docker_jobs_state.json").resolve()
_DOCKER_HELPER_IMAGE = os.getenv("DOCKER_HELPER_IMAGE", "docker:cli")
_NASDAQ_UNIVERSE_FILES: dict[str, Path] = {
    "all": _NASDAQ_SYMBOLS_FILE,
    "midcap": _NASDAQ_MIDCAP_FILE,
    "smallcap": _NASDAQ_SMALLCAP_FILE,
}


def _available_nasdaq_universes() -> List[str]:
    return [key for key, path in _NASDAQ_UNIVERSE_FILES.items() if path.exists()]


@app.get("/", include_in_schema=False)
async def root_redirect() -> RedirectResponse:
    return RedirectResponse(url="/ui/")


def _resolve_reports_path(relative_path: str) -> Path:
    clean_rel = (relative_path or "").lstrip("/")
    candidate = (_REPORTS_DIR / clean_rel).resolve()
    if _REPORTS_DIR == candidate or _REPORTS_DIR in candidate.parents:
        return candidate
    raise HTTPException(status_code=400, detail="Invalid reports path")


def _reports_link(rel_path: str) -> str:
    rel = rel_path.lstrip("/")
    return f"/reports/file/{quote(rel)}"


def _reports_view_link(rel_path: str, *, tail: bool = False, latest: int = 200, refresh: int = 0) -> str:
    rel = quote(rel_path.lstrip("/"))
    return f"/reports/view/{rel}?tail={'1' if tail else '0'}&latest={latest}&refresh={refresh}"


def _render_reports_markdown_line(line: str, current_rel: str) -> str:
    markdown_link_re = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

    def replace_link(match: re.Match[str]) -> str:
        label, href = match.groups()
        if href.startswith(("http://", "https://", "mailto:")):
            link_href = href
        else:
            try:
                target = _resolve_reports_path(str(Path(current_rel).parent / href))
            except HTTPException:
                link_href = html.escape(href)
            else:
                rel = target.relative_to(_REPORTS_DIR).as_posix()
                if target.is_file():
                    link_href = _reports_view_link(rel, tail=rel.endswith(".log"), latest=200, refresh=5 if rel.endswith(".log") else 0)
                else:
                    link_href = _reports_link(rel)
        return f"<a href='{html.escape(link_href, quote=True)}'>{html.escape(label)}</a>"

    escaped_line = html.escape(line)
    return markdown_link_re.sub(replace_link, escaped_line)


_REPORT_CLEANUP_TARGETS: dict[str, list[str]] = {
    "hourly_watchlist": ["hourly_watchlist/hourly_watchlist_*.md"],
    "failed_cycles": ["failed_watchlist_report_cycle_*.json"],
    "investment_cycles": ["investment_analysis_cycle_*.json", "investment_analysis_cycle_*.md"],
    "run_logs": [".cron_state/run_*.log"],
    "cron_logs": [".cron_state/cron_*.log"],
    "latest_aliases": ["*_latest_watchlist_report.json"],
}


class ReportsCleanupRangeRequest(BaseModel):
    date_from: str
    date_to: str
    targets: List[str]
    dry_run: bool = True


class ReportsCleanupAllRequest(BaseModel):
    targets: List[str]
    dry_run: bool = True


class PromptEngineeringSaveRequest(BaseModel):
    prompt: str
    params: dict[str, str]
    include_financial_strategy: bool = False
    financial_strategy_file: str = ""
    financial_strategy_files: List[str] | None = None


class DockerActionRequest(BaseModel):
    container: str
    action: str


class SettingsFileSaveRequest(BaseModel):
    key: str
    content: str


class SettingsFileDiffRequest(BaseModel):
    key: str
    content: str


class CrontabContentRequest(BaseModel):
    user: str
    source: str = "snapshot"
    content: str


class CrontabSaveRequest(BaseModel):
    user: str
    content: str
    target: str = "snapshot"


def _load_docker_jobs_state() -> None:
    if not _DOCKER_JOBS_STATE_FILE.exists():
        return
    try:
        payload = json.loads(_DOCKER_JOBS_STATE_FILE.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            with _DOCKER_JOB_LOCK:
                _DOCKER_JOBS.clear()
                for key, item in payload.items():
                    if isinstance(item, dict):
                        _DOCKER_JOBS[key] = item
    except Exception:
        return


def _save_docker_jobs_state() -> None:
    try:
        _DOCKER_JOBS_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _DOCKER_JOB_LOCK:
            snapshot = json.dumps(_DOCKER_JOBS, ensure_ascii=True, separators=(",", ":"))
        tmp_path = _DOCKER_JOBS_STATE_FILE.with_suffix(".tmp")
        tmp_path.write_text(snapshot, encoding="utf-8")
        tmp_path.replace(_DOCKER_JOBS_STATE_FILE)
    except Exception:
        return


_load_docker_jobs_state()


def _settings_file_specs() -> dict[str, dict[str, str]]:
    return {
        "workspace_env": {
            "label": ".env",
            "kind": "local",
            "path": str((_WORKSPACE_ROOT / ".env").resolve()),
        },
        "docker_compose": {
            "label": "docker-compose.yml",
            "kind": "local",
            "path": str((_WORKSPACE_ROOT / "docker-compose.yml").resolve()),
        },
        "analyst_env": {
            "label": "workspace/investment-analyst-api/.env",
            "kind": "local",
            "path": str((_WORKSPACE_ROOT / "investment-analyst-api" / ".env").resolve()),
        },
        "hermes_config": {
            "label": "Hermes /opt/data/config.yaml",
            "kind": "hermes",
            "path": "/opt/data/config.yaml",
        },
        "brudnopis": {
            "label": "workspace/.brudnopis.sh",
            "kind": "local",
            "path": str((_WORKSPACE_ROOT / ".brudnopis.sh").resolve()),
        },
    }


def _ensure_workspace_local_path(local_path: str) -> Path:
    target = Path(local_path).resolve()
    if _WORKSPACE_ROOT != target and _WORKSPACE_ROOT not in target.parents:
        raise HTTPException(status_code=400, detail="Invalid settings path")
    return target


def _read_local_settings_file(local_path: str) -> str:
    target = _ensure_workspace_local_path(local_path)
    if not target.exists() or not target.is_file():
        return ""
    return target.read_text(encoding="utf-8", errors="replace")


def _write_local_settings_file(local_path: str, content: str) -> None:
    target = _ensure_workspace_local_path(local_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _read_hermes_settings_file(path_in_container: str) -> str:
    container_name = os.getenv("HERMES_CONTAINER_NAME", "hermes")
    cmd = [
        "docker",
        "exec",
        container_name,
        "sh",
        "-lc",
        f"cat {shlex.quote(path_in_container)}",
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=12)
    if result.returncode != 0:
        output = (result.stdout or "").strip()
        if "No such file or directory" in output:
            return ""
        raise HTTPException(status_code=502, detail=f"Failed to read Hermes config: {output or 'unknown error'}")
    return result.stdout or ""


def _write_hermes_settings_file(path_in_container: str, content: str) -> None:
    container_name = os.getenv("HERMES_CONTAINER_NAME", "hermes")
    shell = (
        f"mkdir -p {shlex.quote(str(Path(path_in_container).parent))} "
        f"&& cat > {shlex.quote(path_in_container)}"
    )
    cmd = ["docker", "exec", "-i", container_name, "sh", "-lc", shell]
    result = subprocess.run(cmd, input=content, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=20)
    if result.returncode != 0:
        output = (result.stdout or "").strip()
        raise HTTPException(status_code=502, detail=f"Failed to write Hermes config: {output or 'unknown error'}")


def _settings_backups_dir() -> Path:
    target = (_WORKSPACE_ROOT / "backups").resolve()
    if _WORKSPACE_ROOT != target and _WORKSPACE_ROOT not in target.parents:
        raise HTTPException(status_code=400, detail="Invalid backups path")
    target.mkdir(parents=True, exist_ok=True)
    return target


def _create_settings_backup(key: str, label: str, original_content: str) -> str:
    safe_key = re.sub(r"[^a-zA-Z0-9_.-]+", "_", key).strip("_") or "settings"
    safe_label = re.sub(r"[^a-zA-Z0-9_.-]+", "_", label).strip("_") or "file"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}__{safe_key}__{safe_label}.bak"
    backup_path = _settings_backups_dir() / filename
    backup_path.write_text(original_content, encoding="utf-8")
    return backup_path.relative_to(_WORKSPACE_ROOT).as_posix()


def _settings_file_diff_text(label: str, old_text: str, new_text: str) -> str:
    old_lines = (old_text or "").splitlines()
    new_lines = (new_text or "").splitlines()
    diff_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"{label} (current)",
            tofile=f"{label} (edited)",
            lineterm="",
            n=2,
        )
    )
    if not diff_lines:
        return "No changes."
    return "\n".join(diff_lines)


def _crontab_users() -> list[str]:
    users_env = os.getenv("CRONTAB_SNAPSHOT_USERS", "mbednarski")
    raw_users = [item.strip() for item in users_env.split(",") if item.strip()]
    if not raw_users:
        raw_users = ["mbednarski"]

    users: list[str] = []
    seen: set[str] = set()
    for user in raw_users:
        if user in seen:
            continue
        seen.add(user)
        users.append(user)
    return users


def _sanitize_crontab_user(user: str) -> str:
    normalized = (user or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="Crontab user is required")
    if not re.fullmatch(r"[a-zA-Z0-9_.-]+", normalized):
        raise HTTPException(status_code=400, detail="Invalid crontab user")
    return normalized


def _crontab_snapshot_path(user: str) -> Path:
    safe_user = _sanitize_crontab_user(user)
    return (_REPORTS_DIR / ".cron_state" / f"crontab_{safe_user}.txt").resolve()


def _read_crontab_snapshot(user: str) -> str:
    snapshot_path = _crontab_snapshot_path(user)
    if not snapshot_path.exists() or not snapshot_path.is_file():
        return ""
    return snapshot_path.read_text(encoding="utf-8", errors="replace")


def _write_crontab_snapshot(user: str, content: str) -> Path:
    snapshot_path = _crontab_snapshot_path(user)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(content, encoding="utf-8")
    return snapshot_path


def _crontab_cli_path() -> str:
    crontab_bin = shutil.which("crontab")
    if not crontab_bin:
        raise HTTPException(status_code=503, detail="crontab command is not available")
    return crontab_bin


def _read_system_crontab(user: str) -> tuple[str, str]:
    safe_user = _sanitize_crontab_user(user)
    crontab_bin = _crontab_cli_path()

    attempts: list[list[str]] = [[crontab_bin, "-l", "-u", safe_user]]
    current_user = (os.getenv("USER", "").strip() or os.getenv("USERNAME", "").strip())
    if current_user and safe_user == current_user:
        attempts.append([crontab_bin, "-l"])

    errors: list[str] = []
    for cmd in attempts:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=12,
        )
        combined = "\n".join([result.stdout or "", result.stderr or ""]).strip()
        if result.returncode == 0:
            return (result.stdout or "", " ".join(cmd))

        lowered = combined.lower()
        if "no crontab for" in lowered:
            return ("", " ".join(cmd))
        errors.append(f"{' '.join(cmd)} => {combined or 'exit ' + str(result.returncode)}")

    raise HTTPException(status_code=502, detail="Failed to read system crontab: " + " | ".join(errors))


def _write_system_crontab(user: str, content: str) -> str:
    safe_user = _sanitize_crontab_user(user)
    crontab_bin = _crontab_cli_path()

    attempts: list[list[str]] = [[crontab_bin, "-u", safe_user, "-"]]
    current_user = (os.getenv("USER", "").strip() or os.getenv("USERNAME", "").strip())
    if current_user and safe_user == current_user:
        attempts.append([crontab_bin, "-"])

    errors: list[str] = []
    for cmd in attempts:
        result = subprocess.run(
            cmd,
            input=content,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            return " ".join(cmd)

        combined = "\n".join([result.stdout or "", result.stderr or ""]).strip()
        errors.append(f"{' '.join(cmd)} => {combined or 'exit ' + str(result.returncode)}")

    raise HTTPException(status_code=502, detail="Failed to save system crontab: " + " | ".join(errors))


def _parse_iso_date(raw: str, field_name: str) -> datetime:
    try:
        parsed = datetime.strptime(raw, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name}. Use YYYY-MM-DD format.",
        ) from exc
    return parsed


def _cleanup_window(date_from: str, date_to: str) -> tuple[float, float]:
    start_day = _parse_iso_date(date_from, "date_from")
    end_day = _parse_iso_date(date_to, "date_to")
    if end_day < start_day:
        raise HTTPException(status_code=400, detail="date_to must be >= date_from")

    start_ts = datetime.combine(start_day.date(), dt_time.min).timestamp()
    end_ts = datetime.combine(end_day.date(), dt_time.max).timestamp()
    return start_ts, end_ts


def _resolve_cleanup_targets(requested: List[str]) -> list[str]:
    invalid_targets = [t for t in requested if t not in _REPORT_CLEANUP_TARGETS]
    if invalid_targets:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported targets: {', '.join(sorted(invalid_targets))}",
        )
    if not requested:
        raise HTTPException(status_code=400, detail="At least one target must be selected")
    return requested


def _select_cleanup_files(date_from: str, date_to: str, targets: List[str]) -> list[Path]:
    requested = _resolve_cleanup_targets(targets)
    start_ts, end_ts = _cleanup_window(date_from, date_to)

    matched: list[Path] = []
    for target in requested:
        for pattern in _REPORT_CLEANUP_TARGETS[target]:
            matched.extend(_REPORTS_DIR.glob(pattern))

    unique_files: list[Path] = []
    seen: set[str] = set()
    for path in matched:
        resolved = path.resolve()
        key = str(resolved)
        if key in seen:
            continue
        if not resolved.is_file():
            continue
        if not (_REPORTS_DIR == resolved or _REPORTS_DIR in resolved.parents):
            continue
        seen.add(key)
        unique_files.append(resolved)

    selected: list[Path] = []
    for path in unique_files:
        mtime = path.stat().st_mtime
        if start_ts <= mtime <= end_ts:
            selected.append(path)

    return selected


def _select_cleanup_files_all(targets: List[str]) -> list[Path]:
    requested = _resolve_cleanup_targets(targets)

    matched: list[Path] = []
    for target in requested:
        for pattern in _REPORT_CLEANUP_TARGETS[target]:
            matched.extend(_REPORTS_DIR.glob(pattern))

    unique_files: list[Path] = []
    seen: set[str] = set()
    for path in matched:
        resolved = path.resolve()
        key = str(resolved)
        if key in seen:
            continue
        if not resolved.is_file():
            continue
        if not (_REPORTS_DIR == resolved or _REPORTS_DIR in resolved.parents):
            continue
        seen.add(key)
        unique_files.append(resolved)

    return unique_files


def _resolve_docs_path(relative_path: str) -> Path:
    clean_rel = (relative_path or "").lstrip("/")
    candidate = (_DOCS_DIR / clean_rel).resolve()
    if _DOCS_DIR == candidate or _DOCS_DIR in candidate.parents:
        return candidate
    raise HTTPException(status_code=400, detail="Invalid docs path")


def _resolve_financial_strategy_file(relative_path: str) -> Path:
    clean_rel = (relative_path or "").strip()
    if not clean_rel:
        raise HTTPException(status_code=400, detail="Financial strategy file is required")

    normalized_rel = clean_rel
    if normalized_rel.startswith("docs/"):
        normalized_rel = normalized_rel[len("docs/"):]

    candidate = Path(normalized_rel)
    if not candidate.is_absolute():
        if normalized_rel.startswith("strategies/"):
            candidate = (_DOCS_DIR / normalized_rel).resolve()
        else:
            candidate = (_DOCS_DIR / "strategies" / normalized_rel).resolve()
    else:
        candidate = candidate.resolve()

    strategies_root = (_DOCS_DIR / "strategies").resolve()
    if strategies_root == candidate or strategies_root in candidate.parents:
        if candidate.exists() and candidate.is_file() and candidate.suffix.lower() == ".md":
            return candidate
    raise HTTPException(status_code=400, detail="Invalid financial strategy file")


def _compose_prompt_with_optional_strategy(prompt: str, include_financial_strategy: bool, financial_strategy_file: Any) -> str:
    if not include_financial_strategy:
        return prompt

    if not financial_strategy_file:
        return prompt

    items: List[str]
    if isinstance(financial_strategy_file, (list, tuple, set)):
        items = [str(item) for item in financial_strategy_file if str(item).strip()]
    else:
        items = [str(financial_strategy_file)]

    if not items:
        return prompt

    sections: list[str] = []
    for item in items:
        try:
            strategy_path = _resolve_financial_strategy_file(item)
        except HTTPException:
            continue

        try:
            strategy_text = strategy_path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue

        if not strategy_text:
            continue

        sections.append(
            "=== FINANCIAL STRATEGY ===\n"
            f"Source: {strategy_path.relative_to(_DOCS_DIR).as_posix()}\n\n"
            f"{strategy_text}"
        )

    if not sections:
        return prompt

    return f"{prompt}\n\n" + "\n\n".join(sections)


def _unescape_bash_double_quoted(value: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == "\\" and i + 1 < len(value):
            nxt = value[i + 1]
            if nxt in ('\\', '"'):
                out.append(nxt)
                i += 2
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def _escape_bash_double_quoted(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _load_prompt_engineering_script() -> str:
    script = _WATCHLIST_RUNNER_SCRIPT
    if not script.exists() or not script.is_file():
        raise HTTPException(status_code=404, detail=f"Script not found: {script}")
    return script.read_text(encoding="utf-8", errors="replace")


def _extract_prompt_engineering_config(text: str) -> dict[str, Any]:
    prompt_match = re.search(r'^PROMPT="(.*)"$', text, flags=re.MULTILINE)
    if not prompt_match:
        raise HTTPException(status_code=500, detail="PROMPT variable not found in runner script")

    prompt_value = _unescape_bash_double_quoted(prompt_match.group(1))
    params: list[dict[str, str]] = []
    seen: set[str] = set()
    pattern = re.compile(
        r'^[ \t]*([A-Z][A-Z0-9_]*)="\$\{\1:-([^}]*)\}"(?:[ \t]+#.*)?$',
        re.MULTILINE,
    )
    for match in pattern.finditer(text):
        name, default = match.groups()
        if name in seen:
            continue
        seen.add(name)
        params.append({
            "name": name,
            "default": _unescape_bash_double_quoted(default),
        })

    financial_strategy_enabled = False
    financial_strategy_file = ""
    financial_strategy_files: list[str] = []
    if re.search(r'^FINANCIAL_STRATEGY_ENABLED="(.*)"$', text, flags=re.MULTILINE):
        enabled_match = re.search(r'^FINANCIAL_STRATEGY_ENABLED="(.*)"$', text, flags=re.MULTILINE)
        raw_enabled = _unescape_bash_double_quoted(enabled_match.group(1))
        financial_strategy_enabled = raw_enabled.lower() in {"1", "true", "yes", "on"}
    if re.search(r'^FINANCIAL_STRATEGY_FILE="(.*)"$', text, flags=re.MULTILINE):
        file_match = re.search(r'^FINANCIAL_STRATEGY_FILE="(.*)"$', text, flags=re.MULTILINE)
        financial_strategy_file = _unescape_bash_double_quoted(file_match.group(1))
    if financial_strategy_file:
        financial_strategy_files = [item.strip() for item in financial_strategy_file.split(",") if item.strip()]
    else:
        financial_strategy_files = []

    strategies_root = (_DOCS_DIR / "strategies").resolve()
    available_strategy_files = []
    if strategies_root.exists():
        available_strategy_files = sorted(
            [path.relative_to(_DOCS_DIR).as_posix() for path in strategies_root.rglob("*.md") if path.is_file()]
        )

    return {
        "script_path": str(_WATCHLIST_RUNNER_SCRIPT),
        "prompt": prompt_value,
        "params": params,
        "include_financial_strategy": financial_strategy_enabled,
        "financial_strategy_file": financial_strategy_file,
        "financial_strategy_files": financial_strategy_files,
        "financial_strategy_dir": str(strategies_root),
        "available_financial_strategy_files": available_strategy_files,
    }


def _normalize_prompt_input(prompt: str) -> str:
    clean = (prompt or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if "\n" in clean:
        clean = " ".join(part.strip() for part in clean.split("\n") if part.strip())
    return clean


def _docs_link(rel_path: str) -> str:
    rel = rel_path.lstrip("/")
    return f"/docs-browser/file/{quote(rel)}"


def _load_nasdaq_symbols(universe: str = "all") -> List[str]:
    """Load and normalize NASDAQ symbols from docs files for selected universe."""
    universe_key = (universe or "all").strip().lower()
    source_file = _NASDAQ_UNIVERSE_FILES.get(universe_key)
    if source_file is None:
        raise HTTPException(status_code=400, detail="Invalid NASDAQ universe. Use: all, midcap, smallcap")
    if not source_file.exists():
        raise HTTPException(status_code=404, detail=f"NASDAQ source file not found for universe '{universe_key}'")

    symbols: List[str] = []
    seen: set[str] = set()
    try:
        with source_file.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith("#"):
                    continue

                # Extract the first token (works for plain lists and tabular snapshots).
                symbol = re.split(r"[\s,;|]+", line, maxsplit=1)[0].upper()
                if not symbol or not re.fullmatch(r"[A-Z0-9.\-]+", symbol):
                    continue
                if symbol in seen:
                    continue
                seen.add(symbol)
                symbols.append(symbol)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Cannot read NASDAQ symbols file for '{universe_key}': {exc}") from exc

    return symbols


def _docs_list_link(rel_path: str) -> str:
    rel = rel_path.lstrip("/")
    return f"/docs-browser/list?path={quote(rel)}"


def _render_docs_markdown_line(line: str, current_rel: str) -> str:
    markdown_link_re = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

    def replace_link(match: re.Match[str]) -> str:
        label, href = match.groups()
        if href.startswith(("http://", "https://", "mailto:")):
            link_href = href
        else:
            try:
                target = _resolve_docs_path(str(Path(current_rel).parent / href))
            except HTTPException:
                link_href = html.escape(href)
            else:
                rel = target.relative_to(_DOCS_DIR).as_posix()
                if target.is_file():
                    link_href = f"/docs-browser/file/{quote(rel)}?raw=0"
                else:
                    link_href = _docs_list_link(rel)
        return f"<a href='{html.escape(link_href, quote=True)}'>{html.escape(label)}</a>"

    escaped_line = html.escape(line)
    return markdown_link_re.sub(replace_link, escaped_line)


@app.get("/docs-browser", include_in_schema=False)
async def docs_browser_root_redirect() -> RedirectResponse:
    return RedirectResponse(url="/docs-browser/list")


@app.get("/docs-browser/list", include_in_schema=False)
async def docs_browser_list(path: str = Query(default="")) -> HTMLResponse:
    del path
    entries_map: Dict[str, Path] = {}

    # Root docs files.
    for entry in _DOCS_DIR.iterdir():
        if entry.is_file() and not entry.name.startswith("."):
            rel_key = entry.relative_to(_DOCS_DIR).as_posix()
            entries_map[rel_key] = entry

    # Include curated subfolders used by the team for descriptions, PDFs, and strategy notes.
    for subdir_name in ("descriptions", "describtion", "PDF", "strategies"):
        subdir = _DOCS_DIR / subdir_name
        if not subdir.exists() or not subdir.is_dir():
            continue
        for entry in subdir.rglob("*"):
            if not entry.is_file() or entry.name.startswith("."):
                continue
            rel_key = entry.relative_to(_DOCS_DIR).as_posix()
            entries_map[rel_key] = entry

    entries = sorted(entries_map.values(), key=lambda p: p.relative_to(_DOCS_DIR).as_posix().lower())
    root_rows: List[str] = []
    descriptions_rows: List[str] = []
    pdf_rows: List[str] = []
    strategies_rows: List[str] = []
    other_rows: List[str] = []
    first_link = _docs_link(entries[0].relative_to(_DOCS_DIR).as_posix()) if entries else "about:blank"

    for entry in entries:
        rel = entry.relative_to(_DOCS_DIR).as_posix()
        row = f"<li>[FILE] <a href='{_docs_link(rel)}' target='docs-frame'>{rel}</a></li>"
        if "/" not in rel:
            root_rows.append(row)
        elif rel.startswith("descriptions/") or rel.startswith("describtion/"):
            descriptions_rows.append(row)
        elif rel.startswith("PDF/"):
            pdf_rows.append(row)
        elif rel.startswith("strategies/"):
            strategies_rows.append(row)
        else:
            other_rows.append(row)

    section_blocks: List[str] = []

    if root_rows:
        section_blocks.append("<div class='docs-section'><div class='docs-section-title'>docs/</div><ul style='margin:0; padding-left:18px;'>" + "".join(root_rows) + "</ul></div>")
    if descriptions_rows:
        section_blocks.append("<div class='docs-section'><div class='docs-section-title'>docs/descriptions/</div><ul style='margin:0; padding-left:18px;'>" + "".join(descriptions_rows) + "</ul></div>")
    if pdf_rows:
        section_blocks.append("<div class='docs-section'><div class='docs-section-title'>docs/PDF/</div><ul style='margin:0; padding-left:18px;'>" + "".join(pdf_rows) + "</ul></div>")
    if strategies_rows:
        section_blocks.append("<div class='docs-section'><div class='docs-section-title'>docs/strategies/</div><ul style='margin:0; padding-left:18px;'>" + "".join(strategies_rows) + "</ul></div>")
    if other_rows:
        section_blocks.append("<div class='docs-section'><div class='docs-section-title'>other/</div><ul style='margin:0; padding-left:18px;'>" + "".join(other_rows) + "</ul></div>")

    body = "".join(section_blocks) if section_blocks else "<div class='docs-section'><ul style='margin:0; padding-left:18px;'><li>empty</li></ul></div>"
    html_doc = f"""
<html><head><title>docs index</title></head>
<body style='margin:0; font-family: ui-monospace, monospace; background:#07090c; color:#d7dde4; min-height:100vh; display:flex; flex-direction:column;'>
    <style>
        .docs-wrap {{ flex:1; display:flex; flex-direction:column; min-height:0; }}
        .docs-sidebar {{ font-size: 11px; line-height: 1.35; }}
        .docs-section {{ margin-bottom: 12px; }}
        .docs-section-title {{ color:#ffb000; margin:0 0 6px 0; font-weight:700; }}
        .docs-sidebar li {{ margin-bottom: 4px; overflow-wrap: anywhere; word-break: break-word; }}
        .docs-sidebar a {{ display: inline-block; max-width: 100%; white-space: normal; overflow-wrap: anywhere; word-break: break-word; }}
        .footer {{ margin-top:auto; border-top:1px solid #1f2630; padding:10px 14px; display:flex; justify-content:flex-end; color:#6a7480; font-size:12px; }}
        .footer a {{ color:#9ecbff; text-decoration:none; }}
        .footer a.brand-link {{ color:#ffb000; }}
        .footer a:hover {{ color:#ffb000; text-decoration:underline; }}
    </style>
    <div class='docs-wrap'>
        <div style='display:flex; flex:1; min-height:0;'>
                <aside class='docs-sidebar' style='width:38%; min-width:320px; max-width:520px; border-right:1px solid #1f2630; padding:14px; overflow:auto; box-sizing:border-box;'>
            <div style='margin-bottom:8px;'><a style='color:#ffb000' href='/ui/'>[back to UI]</a></div>
            <h3 style='margin:0 0 8px 0;'>docs/</h3>
            <div style='margin:6px 0 10px 0; color:#6a7480;'>Click a file to load it in the frame.</div>
            <div>{body}</div>
        </aside>
        <main style='flex:1; padding:14px; box-sizing:border-box;'>
            <iframe
                name='docs-frame'
                src='{first_link}'
                style='width:100%; height:100%; border:1px solid #1f2630; background:#0d1117;'
                title='Docs preview'
            ></iframe>
        </main>
        </div>
        <div class='footer'>
            <span>(c) 2026 <a class='brand-link' href='https://honeybarrel.org'>HONEY-BARREL Labs</a>  *  <a href='/ui/'>UI DASHBOARD</a></span>
        </div>
    </div>
</body></html>
"""
    return HTMLResponse(content=html_doc)


@app.get("/docs-browser/file/{doc_path:path}", include_in_schema=False)
async def docs_browser_file(doc_path: str, raw: int = Query(default=0, ge=0, le=1)) -> HTMLResponse:
    target = _resolve_docs_path(doc_path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Doc file not found")

    raw_text = target.read_text(encoding="utf-8", errors="replace")
    rel = target.relative_to(_DOCS_DIR).as_posix()
    if rel.lower().endswith(".md") and raw == 0:
        markdown_source_json = json.dumps(raw_text)
        rendered_link = f"/docs-browser/file/{quote(rel)}?raw=0"
        raw_link = f"/docs-browser/file/{quote(rel)}?raw=1"
        html_doc = f"""
<html>
<head>
    <title>docs: {rel}</title>
    <meta charset='utf-8' />
    <meta name='viewport' content='width=device-width, initial-scale=1.0' />
    <link rel='stylesheet' href='https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.10.0/styles/github-dark.min.css' />
    <style>
        body {{ margin:0; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; background:#07090c; color:#d7dde4; padding:14px; box-sizing:border-box; min-height:100vh; display:flex; flex-direction:column; }}
        .doc-wrap {{ flex:1; }}
        h3 {{ margin:8px 0 12px 0; color:#d7dde4; }}
        .doc {{ border:1px solid #1f2630; background:#0d1117; padding:14px; line-height:1.55; }}
        .doc h1, .doc h2, .doc h3, .doc h4 {{ color:#ffb000; margin-top:1.1em; margin-bottom:0.5em; }}
        .doc p, .doc li {{ color:#d7dde4; }}
        .doc a {{ color:#9ecbff; }}
        .doc pre {{ padding:10px; border:1px solid #1f2630; border-radius:4px; overflow:auto; background:#0b0f14; }}
        .doc code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
        .footer {{ margin-top:auto; border-top:1px solid #1f2630; padding-top:10px; display:flex; justify-content:flex-end; color:#6a7480; font-size:12px; }}
        .footer a {{ color:#9ecbff; text-decoration:none; }}
        .footer a.brand-link {{ color:#ffb000; }}
        .footer a:hover {{ color:#ffb000; text-decoration:underline; }}
    </style>
</head>
<body>
    <div class='doc-wrap'>
    <div style='display:flex; gap:14px; align-items:center; margin-bottom:8px;'>
        <span style='color:#6a7480;'>view:</span>
        <a style='color:#9ecbff; text-decoration:none;' href='{rendered_link}'>Rendered</a>
        <a style='color:#9ecbff; text-decoration:none;' href='{raw_link}'>Raw</a>
    </div>
    <h3>{rel}</h3>
    <div class='doc' id='doc-content'>Loading markdown preview...</div>

    <script src='https://cdnjs.cloudflare.com/ajax/libs/marked/12.0.2/marked.min.js'></script>
    <script src='https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.10.0/highlight.min.js'></script>
    <script>
        const src = {markdown_source_json};
        const root = document.getElementById('doc-content');
        marked.setOptions({{
            gfm: true,
            breaks: false,
            highlight: function(code, lang) {{
                if (lang && hljs.getLanguage(lang)) {{
                    return hljs.highlight(code, {{ language: lang }}).value;
                }}
                return hljs.highlightAuto(code).value;
            }}
        }});
        root.innerHTML = marked.parse(src);
    </script>
    </div>
    <div class='footer'>
        <span>(c) 2026 <a class='brand-link' href='https://honeybarrel.org'>HONEY-BARREL Labs</a>  *  <a href='/ui/'>UI DASHBOARD</a></span>
    </div>
</body>
</html>
"""
        return HTMLResponse(content=html_doc)

    rendered_link = f"/docs-browser/file/{quote(rel)}?raw=0"
    raw_link = f"/docs-browser/file/{quote(rel)}?raw=1"

    if rel.lower().endswith(".md") and raw == 1:
        raw_lines = raw_text.splitlines()
        rendered_raw = "<br/>".join(_render_docs_markdown_line(line, rel) for line in raw_lines)
        html_doc = f"""
<html>
<head>
    <title>docs raw: {rel}</title>
    <meta charset='utf-8' />
    <meta name='viewport' content='width=device-width, initial-scale=1.0' />
    <style>
        body {{ margin:0; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; background:#07090c; color:#d7dde4; padding:14px; box-sizing:border-box; min-height:100vh; display:flex; flex-direction:column; }}
        .doc-wrap {{ flex:1; }}
        h3 {{ margin:8px 0 12px 0; color:#d7dde4; }}
        .doc {{ border:1px solid #1f2630; background:#0d1117; padding:14px; line-height:1.55; white-space:pre-wrap; overflow-wrap:anywhere; word-break:break-word; }}
        .doc a {{ color:#9ecbff; text-decoration:none; }}
        .doc a:hover {{ color:#ffb000; text-decoration:underline; }}
        .footer {{ margin-top:auto; border-top:1px solid #1f2630; padding-top:10px; display:flex; justify-content:flex-end; color:#6a7480; font-size:12px; }}
        .footer a {{ color:#9ecbff; text-decoration:none; }}
        .footer a.brand-link {{ color:#ffb000; }}
        .footer a:hover {{ color:#ffb000; text-decoration:underline; }}
    </style>
</head>
<body>
    <div class='doc-wrap'>
    <div style='display:flex; gap:14px; align-items:center; margin-bottom:8px;'>
        <span style='color:#6a7480;'>view:</span>
        <a style='color:#9ecbff; text-decoration:none;' href='{rendered_link}'>Rendered</a>
        <a style='color:#9ecbff; text-decoration:none;' href='{raw_link}'>Raw</a>
    </div>
    <h3>{rel}</h3>
    <div class='doc'>{rendered_raw}</div>
    </div>
    <div class='footer'>
        <span>(c) 2026 <a class='brand-link' href='https://honeybarrel.org'>HONEY-BARREL Labs</a>  *  <a href='/ui/'>UI DASHBOARD</a></span>
    </div>
</body>
</html>
"""
        return HTMLResponse(content=html_doc)

    escaped_raw = html.escape(raw_text)
    html_doc = f"""
<html>
<head>
    <title>docs raw: {rel}</title>
    <meta charset='utf-8' />
    <meta name='viewport' content='width=device-width, initial-scale=1.0' />
    <style>
        body {{ margin:0; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; background:#07090c; color:#d7dde4; padding:14px; box-sizing:border-box; min-height:100vh; display:flex; flex-direction:column; }}
        .doc-wrap {{ flex:1; }}
        h3 {{ margin:8px 0 12px 0; color:#d7dde4; }}
        pre {{ border:1px solid #1f2630; background:#0d1117; padding:14px; line-height:1.45; margin:0; overflow:auto; white-space:pre-wrap; overflow-wrap:anywhere; word-break:break-word; }}
        .footer {{ margin-top:auto; border-top:1px solid #1f2630; padding-top:10px; display:flex; justify-content:flex-end; color:#6a7480; font-size:12px; }}
        .footer a {{ color:#9ecbff; text-decoration:none; }}
        .footer a.brand-link {{ color:#ffb000; }}
        .footer a:hover {{ color:#ffb000; text-decoration:underline; }}
    </style>
</head>
<body>
    <div class='doc-wrap'>
    <div style='display:flex; gap:14px; align-items:center; margin-bottom:8px;'>
        <span style='color:#6a7480;'>view:</span>
        <a style='color:#9ecbff; text-decoration:none;' href='{rendered_link}'>Rendered</a>
        <a style='color:#9ecbff; text-decoration:none;' href='{raw_link}'>Raw</a>
    </div>
    <h3>{rel}</h3>
    <pre>{escaped_raw}</pre>
    </div>
    <div class='footer'>
        <span>(c) 2026 <a class='brand-link' href='https://honeybarrel.org'>HONEY-BARREL Labs</a>  *  <a href='/ui/'>UI DASHBOARD</a></span>
    </div>
</body>
</html>
"""
    return HTMLResponse(content=html_doc)


@app.get("/api/docs/raw")
async def api_docs_raw(path: str = Query(...)) -> Response:
    """Return raw docs file content as plain text for in-app previews."""
    target = _resolve_docs_path(path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Doc file not found")

    raw_text = target.read_text(encoding="utf-8", errors="replace")
    return Response(content=raw_text, media_type="text/plain; charset=utf-8")


@app.get("/ui/reports", include_in_schema=False)
async def ui_reports() -> HTMLResponse:
    if not _REPORTS_DIR.exists():
        return HTMLResponse("<h1>Reports directory not found</h1>", status_code=404)

    latest_json = sorted(
        _REPORTS_DIR.glob("*_latest_watchlist_report.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:20]
    hourly_reports = sorted(
        (_REPORTS_DIR / "hourly_watchlist").glob("hourly_watchlist_*.md") if (_REPORTS_DIR / "hourly_watchlist").exists() else [],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:30]
    cron_logs = sorted(
        (_REPORTS_DIR / ".cron_state").glob("cron_*.log") if (_REPORTS_DIR / ".cron_state").exists() else [],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:50]
    run_logs = sorted(
        (_REPORTS_DIR / ".cron_state").glob("run_*.log") if (_REPORTS_DIR / ".cron_state").exists() else [],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:80]

    def to_list(items: list[Path]) -> str:
        if not items:
            return "<li class='muted'>none</li>"
        rows = []
        for item in items:
            rel = item.relative_to(_REPORTS_DIR).as_posix()
            rows.append(f"<li><a href='{_reports_view_link(rel, tail=rel.endswith('.log'), latest=200, refresh=5 if rel.endswith('.log') else 0)}'>{rel}</a></li>")
        return "".join(rows)

    investment_cycles = sorted(
        _REPORTS_DIR.glob("investment_analysis_cycle_*.*"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:30]

    failed_watchlist_cycles = sorted(
        _REPORTS_DIR.glob("failed_watchlist_report_cycle_*.*"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:30]

    success_investment_cycles_count = len(list(_REPORTS_DIR.glob("investment_analysis_cycle_*.json")))
    failed_investment_cycles_count = len(list(_REPORTS_DIR.glob("failed_watchlist_report_cycle_*.json")))
    total_investment_cycles_count = success_investment_cycles_count + failed_investment_cycles_count
    success_investment_cycles_rate = (
        round((success_investment_cycles_count / total_investment_cycles_count) * 100.0, 1)
        if total_investment_cycles_count > 0
        else 0.0
    )

    html = f"""
<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>HB Reports Navigator</title>
  <style>
    :root {{ --bg:#07090c; --bg2:#0d1117; --border:#1f2630; --text:#d7dde4; --muted:#6a7480; --amber:#ffb000; }}
    body {{ margin:0; background:var(--bg); color:var(--text); font:13px/1.4 'JetBrains Mono', ui-monospace, monospace; }}
    .wrap {{ max-width:1200px; margin:0 auto; padding:16px; }}
    .title {{ color:var(--amber); font-weight:700; letter-spacing:0.4px; }}
    .muted {{ color:var(--muted); }}
    .grid {{ display:grid; grid-template-columns:repeat(2, minmax(320px, 1fr)); gap:12px; }}
    .card {{ background:var(--bg2); border:1px solid var(--border); padding:10px 12px; }}
    .card.featured {{ border-color: var(--amber); box-shadow: 0 0 0 1px rgba(255, 176, 0, 0.16) inset; }}
    .card h3 {{ margin:0 0 8px 0; font-size:12px; color:var(--amber); text-transform:uppercase; letter-spacing:0.8px; }}
    ul {{ margin:0; padding-left:16px; max-height:280px; overflow:auto; }}
    li {{ margin:2px 0; }}
    a {{ color:#9ecbff; text-decoration:none; }}
    a:hover {{ color:var(--amber); text-decoration:underline; }}
    .quick {{ display:flex; flex-wrap:wrap; gap:10px; margin:10px 0 14px 0; }}
    .quick a {{ border:1px solid var(--border); padding:4px 8px; border-radius:2px; background:var(--bg2); }}
        .kpi-grid {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr)); gap:12px; margin:0 0 12px 0; }}
        .kpi {{ background:var(--bg2); border:1px solid var(--border); padding:10px 12px; }}
        .kpi h3 {{ margin:0 0 6px 0; font-size:11px; color:var(--muted); text-transform:uppercase; letter-spacing:0.8px; }}
        .kpi .value {{ font-size:30px; font-weight:700; line-height:1; color:var(--amber); }}
        .kpi.failed .value {{ color:#ff6b6b; }}
        .kpi.rate .value {{ color:#8fe3a4; }}
        .kpi .link {{ margin-top:8px; font-size:12px; }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"title\">HONEY-BARREL // UI REPORTS NAVIGATOR</div>
    <div class=\"muted\">Quick access to reports, hourly watchlist snapshots, cron logs, and run logs.</div>
    <div class=\"quick\">
      <a href=\"/reports/list?path=\">reports/</a>
            <a href="/live-watchlist" target="_blank" rel="noopener noreferrer">Live Watchlist</a>
      <a href=\"/reports/list?path=hourly_watchlist\">reports/hourly_watchlist/</a>
      <a href=\"/reports/match?pattern=.cron_state/cron_*.log\">reports/.cron_state/cron_*.log</a>
      <a href=\"/reports/match?pattern=.cron_state/run_*.log\">reports/.cron_state/run_*.log</a>
      <a href=\"/ui/\">back to dashboard</a>
    </div>
        <div class="kpi-grid">
            <section class="kpi">
                <h3>success investment_cycles</h3>
                <div class="value">{success_investment_cycles_count}</div>
                <div class="link"><a href="/reports/match?pattern=investment_analysis_cycle_*.json">open success cycles</a></div>
            </section>
            <section class="kpi failed">
                <h3>failed investment_cycles</h3>
                <div class="value">{failed_investment_cycles_count}</div>
                <div class="link"><a href="/reports/match?pattern=failed_watchlist_report_cycle_*.json">open failed cycles</a></div>
            </section>
            <section class="kpi rate">
                <h3>success rate</h3>
                <div class="value">{success_investment_cycles_rate}%</div>
                <div class="link"><a href="/reports/match?pattern=investment_analysis_cycle_*.json">based on investment cycles</a></div>
            </section>
        </div>
    <div class=\"grid\">
      <section class=\"card\">
        <h3>Latest Daily Aliases</h3>
        <ul>{to_list(latest_json)}</ul>
      </section>
            <section class="card">
                <h3>Daily Investment Generator Log</h3>
                <ul>
                    <li><a href="/reports/file/.cron_state/daily_investment_watchlist_report_generator.log">.cron_state/daily_investment_watchlist_report_generator.log</a></li>
                </ul>
            </section>
            <section class="card featured">
                <h3>Daily Investment Generator Viewer</h3>
                <ul>
                    <li><a href="/reports/view/.cron_state/daily_investment_watchlist_report_generator.log?tail=1&latest=200&refresh=5&alerts_only=1">view/.cron_state/daily_investment_watchlist_report_generator.log</a></li>
                </ul>
            </section>
            <section class="card">
                <h3>Failed Watchlist Cycles</h3>
                <ul>{to_list(failed_watchlist_cycles)}</ul>
            </section>
            <section class="card">
                <h3>Investment Cycles</h3>
                <ul>{to_list(investment_cycles)}</ul>
            </section>
      <section class=\"card\">
        <h3>Hourly Watchlist</h3>
        <ul>{to_list(hourly_reports)}</ul>
      </section>
      <section class=\"card\">
        <h3>Cron Logs</h3>
        <ul>{to_list(cron_logs)}</ul>
      </section>
      <section class=\"card\">
        <h3>Run Logs</h3>
        <ul>{to_list(run_logs)}</ul>
      </section>
    </div>
  </div>
</body>
</html>
"""
    return HTMLResponse(content=html)


@app.get("/live-watchlist", include_in_schema=False)
async def live_watchlist() -> HTMLResponse:
    return HTMLResponse(content=build_html_page())


@app.get("/api/snapshot", include_in_schema=False)
async def api_live_watchlist_snapshot(mode: str = "all") -> dict[str, Any]:
    normalized_mode = (mode or "all").strip().lower()
    if normalized_mode not in {"all", "buy", "sell", "hold", "buy_sell"}:
        normalized_mode = "all"

    cron_snapshot_file = os.getenv("CRON_SNAPSHOT_FILE", str(_WORKSPACE_ROOT / "reports" / ".cron_state" / "crontab_mbednarski.txt"))
    reports_dir = os.getenv("REPORTS_DIR", str(_WORKSPACE_ROOT / "reports"))
    return build_snapshot(cron_snapshot_file, reports_dir, normalized_mode, str(_WORKSPACE_ROOT))


@app.get("/report", include_in_schema=False)
async def report_view(path: str) -> Response:
    rel_path = unquote((path or "").strip()).replace("\\", "/")
    if not rel_path.startswith("reports/"):
        raise HTTPException(status_code=400, detail="invalid report path")

    abs_path = (_WORKSPACE_ROOT / rel_path).resolve()
    if not abs_path.is_file() or _WORKSPACE_ROOT not in abs_path.parents and abs_path != _WORKSPACE_ROOT:
        raise HTTPException(status_code=404, detail="report not found")

    if abs_path.suffix == ".json":
        content_type = "application/json; charset=utf-8"
    elif abs_path.suffix == ".md":
        content_type = "text/markdown; charset=utf-8"
    else:
        content_type = "text/plain; charset=utf-8"

    return Response(content=abs_path.read_bytes(), media_type=content_type)


@app.post("/api/reports/cleanup-range")
async def api_reports_cleanup_range(payload: ReportsCleanupRangeRequest) -> dict[str, Any]:
    if not _REPORTS_DIR.exists():
        raise HTTPException(status_code=404, detail="Reports directory not found")

    requested = _resolve_cleanup_targets(payload.targets or [])
    selected = _select_cleanup_files(payload.date_from, payload.date_to, requested)

    deleted_rel: list[str] = []
    failed: list[dict[str, str]] = []
    if not payload.dry_run:
        for path in selected:
            rel = path.relative_to(_REPORTS_DIR).as_posix()
            try:
                path.unlink()
                deleted_rel.append(rel)
            except Exception as exc:
                failed.append({"path": rel, "error": str(exc)})

    preview_rel = [p.relative_to(_REPORTS_DIR).as_posix() for p in selected[:300]]
    return {
        "success": True,
        "dry_run": payload.dry_run,
        "date_from": payload.date_from,
        "date_to": payload.date_to,
        "targets": requested,
        "matched_count": len(selected),
        "in_range_count": len(selected),
        "deleted_count": len(deleted_rel),
        "failed_count": len(failed),
        "preview": preview_rel,
        "deleted": deleted_rel[:300],
        "failed": failed[:100],
    }


@app.get("/api/reports/investment-cycles-kpi")
async def api_reports_investment_cycles_kpi() -> dict[str, Any]:
    if not _REPORTS_DIR.exists():
        raise HTTPException(status_code=404, detail="Reports directory not found")

    success_investment_cycles_count = len(list(_REPORTS_DIR.glob("investment_analysis_cycle_*.json")))
    failed_investment_cycles_count = len(list(_REPORTS_DIR.glob("failed_watchlist_report_cycle_*.json")))
    total_investment_cycles_count = success_investment_cycles_count + failed_investment_cycles_count
    success_rate_percent = (
        round((success_investment_cycles_count / total_investment_cycles_count) * 100.0, 1)
        if total_investment_cycles_count > 0
        else 0.0
    )

    return {
        "success": True,
        "success_investment_cycles": success_investment_cycles_count,
        "failed_investment_cycles": failed_investment_cycles_count,
        "total_investment_cycles": total_investment_cycles_count,
        "success_rate_percent": success_rate_percent,
    }


@app.post("/api/reports/cleanup-range-export")
async def api_reports_cleanup_range_export(payload: ReportsCleanupRangeRequest) -> Response:
    if not _REPORTS_DIR.exists():
        raise HTTPException(status_code=404, detail="Reports directory not found")

    requested = _resolve_cleanup_targets(payload.targets or [])
    selected = _select_cleanup_files(payload.date_from, payload.date_to, requested)

    header = "path,mtime_iso,size_bytes"
    rows = [header]
    for path in selected:
        rel = path.relative_to(_REPORTS_DIR).as_posix()
        stat = path.stat()
        mtime_iso = datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")
        rows.append(f"\"{rel}\",\"{mtime_iso}\",{stat.st_size}")

    csv_text = "\n".join(rows) + "\n"
    filename = f"reports_cleanup_{payload.date_from}_to_{payload.date_to}.csv"
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Cache-Control": "no-store",
        },
    )


@app.post("/api/reports/cleanup-all")
async def api_reports_cleanup_all(payload: ReportsCleanupAllRequest) -> dict[str, Any]:
    if not _REPORTS_DIR.exists():
        raise HTTPException(status_code=404, detail="Reports directory not found")

    requested = _resolve_cleanup_targets(payload.targets or [])
    selected = _select_cleanup_files_all(requested)

    deleted_rel: list[str] = []
    failed: list[dict[str, str]] = []
    if not payload.dry_run:
        for path in selected:
            rel = path.relative_to(_REPORTS_DIR).as_posix()
            try:
                path.unlink()
                deleted_rel.append(rel)
            except Exception as exc:
                failed.append({"path": rel, "error": str(exc)})

    preview_rel = [p.relative_to(_REPORTS_DIR).as_posix() for p in selected[:300]]
    return {
        "success": True,
        "dry_run": payload.dry_run,
        "targets": requested,
        "matched_count": len(selected),
        "deleted_count": len(deleted_rel),
        "failed_count": len(failed),
        "preview": preview_rel,
        "deleted": deleted_rel[:300],
        "failed": failed[:100],
    }


@app.get("/reports", include_in_schema=False)
async def reports_root_redirect() -> RedirectResponse:
    return RedirectResponse(url="/ui/reports")


@app.get("/reports/stack-summary", include_in_schema=False)
async def reports_stack_summary() -> HTMLResponse:
        cron_state = _REPORTS_DIR / ".cron_state"
        hourly_dir = _REPORTS_DIR / "hourly_watchlist"

        def latest_runs_per_hour() -> Optional[int]:
            if not hourly_dir.exists():
                return None

            candidates = sorted(
                hourly_dir.glob("hourly_watchlist_*.md"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            runs_re = re.compile(r"^-\s*Runs in last hour:\s*(\d+)\s*$", re.IGNORECASE)
            for report in candidates:
                try:
                    text = report.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue

                for line in text.splitlines():
                    match = runs_re.match(line.strip())
                    if match:
                        return int(match.group(1))
            return None

        def average_run_duration_seconds(limit: int = 400) -> Optional[float]:
            duration_re = re.compile(r"duration_seconds=([0-9]+)")
            durations: list[int] = []

            generator_log = cron_state / "daily_investment_watchlist_report_generator.log"
            if generator_log.exists():
                try:
                    text = generator_log.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    text = ""

                matches = duration_re.findall(text)
                if matches:
                    # Use recent samples to reflect current runtime behavior.
                    durations.extend(int(value) for value in matches[-limit:])

            if not durations and cron_state.exists():
                run_logs = sorted(
                    cron_state.glob("run_*.log"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )[:limit]

                for run_log in run_logs:
                    try:
                        text = run_log.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        continue

                    matches = duration_re.findall(text)
                    if not matches:
                        continue
                    # Use the last duration marker as the final duration for a run file.
                    durations.append(int(matches[-1]))

            if not durations:
                return None
            return float(statistics.mean(durations))

        latest_aliases_count = len(list(_REPORTS_DIR.glob("*_latest_watchlist_report.json")))
        investment_cycle_json_count = len(list(_REPORTS_DIR.glob("investment_analysis_cycle_*.json")))
        investment_cycle_md_count = len(list(_REPORTS_DIR.glob("investment_analysis_cycle_*.md")))
        failed_cycle_count = len(list(_REPORTS_DIR.glob("failed_watchlist_report_cycle_*.json")))
        hourly_report_count = len(list(hourly_dir.glob("hourly_watchlist_*.md"))) if hourly_dir.exists() else 0
        cron_log_count = len(list(cron_state.glob("cron_*.log"))) if cron_state.exists() else 0
        run_log_count = len(list(cron_state.glob("run_*.log"))) if cron_state.exists() else 0
        docs_count = len(list(_DOCS_DIR.glob("*"))) if _DOCS_DIR.exists() else 0
        runs_per_hour = latest_runs_per_hour()
        avg_run_duration_sec = average_run_duration_seconds()

        order_sent_count = 0
        order_success_count = 0
        order_failed_count = 0
        success_statuses = {"accepted", "filled", "partially_filled", "new"}
        failed_statuses = {"rejected", "canceled", "cancelled", "expired", "suspended", "stopped", "failed", "error"}

        for artifact in _REPORTS_DIR.glob("investment_analysis_cycle_*.json"):
            try:
                payload = json.loads(artifact.read_text(encoding="utf-8", errors="replace"))
            except Exception:
                continue

            status = str(payload.get("order_status", "")).strip().lower()
            order_id = str(payload.get("order_id", "")).strip().lower()
            executed_write = bool(payload.get("executed_write", False))
            sent = executed_write or (order_id not in {"", "none", "null"})

            if not sent:
                continue

            order_sent_count += 1
            if status in success_statuses:
                order_success_count += 1
            elif status in failed_statuses:
                order_failed_count += 1

        generated_at = time.strftime("%Y-%m-%d %H:%M:%S %Z")

        rows = [
                ("Latest Daily Aliases", latest_aliases_count, "/reports/match?pattern=*_latest_watchlist_report.json"),
            (
                "Runs / hour (latest)",
                runs_per_hour if runs_per_hour is not None else "n/a",
                "/reports/list?path=hourly_watchlist",
            ),
            (
                "Avg Single Run Duration (sec)",
                f"{avg_run_duration_sec:.1f}" if avg_run_duration_sec is not None else "n/a",
                "/reports/match?pattern=.cron_state/run_*.log",
            ),
            ("Orders Sent", order_sent_count, "/reports/match?pattern=investment_analysis_cycle_*.json"),
            ("Orders Successful", order_success_count, "/reports/match?pattern=investment_analysis_cycle_*.json"),
            ("Orders Failed", order_failed_count, "/reports/match?pattern=failed_watchlist_report_cycle_*.json"),
                ("Investment Cycles (.json)", investment_cycle_json_count, "/reports/match?pattern=investment_analysis_cycle_*.json"),
                ("Investment Cycles (.md)", investment_cycle_md_count, "/reports/match?pattern=investment_analysis_cycle_*.md"),
                ("Failed Watchlist Cycles", failed_cycle_count, "/reports/match?pattern=failed_watchlist_report_cycle_*.json"),
                ("Hourly Watchlist Reports", hourly_report_count, "/reports/list?path=hourly_watchlist"),
                ("Cron Logs", cron_log_count, "/reports/match?pattern=.cron_state/cron_*.log"),
                ("Run Logs", run_log_count, "/reports/match?pattern=.cron_state/run_*.log"),
                ("Docs Files", docs_count, "/docs-browser/list"),
        ]

        table_rows = "".join(
                f"<tr><td>{html.escape(name)}</td><td class='num'>{count}</td><td><a href='{link}'>open</a></td></tr>"
                for name, count, link in rows
        )

        html_doc = f"""
<html><head><title>HB Stack Summary</title></head>
<body style='font-family: ui-monospace, monospace; background:#07090c; color:#d7dde4; padding:14px;'>
    <div><a style='color:#ffb000' href='/ui/reports'>[back to UI/reports]</a></div>
    <h3 style='margin:8px 0;'>Honey-Barrel Stack Summary Counters</h3>
    <div style='margin:6px 0 12px 0; color:#6a7480;'>Generated: {generated_at}</div>
    <table style='width:100%; border-collapse:collapse; background:#0d1117; border:1px solid #1f2630;'>
        <thead>
            <tr>
                <th style='text-align:left; border-bottom:1px solid #1f2630; padding:8px;'>Counter</th>
                <th style='text-align:right; border-bottom:1px solid #1f2630; padding:8px;'>Value</th>
                <th style='text-align:left; border-bottom:1px solid #1f2630; padding:8px;'>Link</th>
            </tr>
        </thead>
        <tbody>
            {table_rows}
        </tbody>
    </table>
    <style>
        td {{ padding:8px; border-top:1px solid #1f2630; }}
        .num {{ text-align:right; color:#ffb000; font-weight:700; }}
        a {{ color:#9ecbff; text-decoration:none; }}
        a:hover {{ color:#ffb000; text-decoration:underline; }}
    </style>
</body></html>
"""
        return HTMLResponse(content=html_doc)


@app.get("/reports/crontabs", include_in_schema=False)
async def reports_crontabs() -> HTMLResponse:
    return RedirectResponse(url="/ui/crontabs.html")


@app.get("/api/crontabs/list", include_in_schema=False)
async def api_crontabs_list() -> dict[str, Any]:
    users = _crontab_users()
    has_cli = bool(shutil.which("crontab"))

    rows: list[dict[str, Any]] = []
    for user in users:
        snapshot_path = _crontab_snapshot_path(user)
        exists = snapshot_path.exists() and snapshot_path.is_file()
        rel_path = snapshot_path.relative_to(_WORKSPACE_ROOT).as_posix() if _WORKSPACE_ROOT in snapshot_path.parents else snapshot_path.as_posix()
        rows.append(
            {
                "user": user,
                "label": f"crontab ({user})",
                "snapshot_path": rel_path,
                "snapshot_exists": bool(exists),
                "system_cli_available": has_cli,
            }
        )

    return {
        "success": True,
        "users": rows,
        "timestamp": int(time.time()),
    }


@app.get("/api/crontabs/content", include_in_schema=False)
async def api_crontabs_content(user: str, source: str = Query(default="snapshot")) -> dict[str, Any]:
    safe_user = _sanitize_crontab_user(user)
    source_name = (source or "snapshot").strip().lower()
    if source_name not in {"snapshot", "system"}:
        raise HTTPException(status_code=400, detail="Unsupported crontab source")

    command_used = ""
    if source_name == "snapshot":
        content = _read_crontab_snapshot(safe_user)
    else:
        content, command_used = _read_system_crontab(safe_user)

    snapshot_path = _crontab_snapshot_path(safe_user)
    rel_path = snapshot_path.relative_to(_WORKSPACE_ROOT).as_posix() if _WORKSPACE_ROOT in snapshot_path.parents else snapshot_path.as_posix()
    return {
        "success": True,
        "user": safe_user,
        "source": source_name,
        "content": content,
        "snapshot_path": rel_path,
        "command": command_used,
        "timestamp": int(time.time()),
    }


@app.post("/api/crontabs/diff", include_in_schema=False)
async def api_crontabs_diff(payload: CrontabContentRequest) -> dict[str, Any]:
    safe_user = _sanitize_crontab_user(payload.user)
    source_name = (payload.source or "snapshot").strip().lower()
    if source_name not in {"snapshot", "system"}:
        raise HTTPException(status_code=400, detail="Unsupported crontab source")

    if source_name == "snapshot":
        current_content = _read_crontab_snapshot(safe_user)
    else:
        current_content, _ = _read_system_crontab(safe_user)

    edited_content = payload.content if isinstance(payload.content, str) else ""
    diff_text = _settings_file_diff_text(f"crontab {safe_user} ({source_name})", current_content, edited_content)

    return {
        "success": True,
        "user": safe_user,
        "source": source_name,
        "changed": current_content != edited_content,
        "diff": diff_text,
        "timestamp": int(time.time()),
    }


@app.post("/api/crontabs/save", include_in_schema=False)
async def api_crontabs_save(payload: CrontabSaveRequest) -> dict[str, Any]:
    safe_user = _sanitize_crontab_user(payload.user)
    target = (payload.target or "snapshot").strip().lower()
    if target not in {"snapshot", "system", "both"}:
        raise HTTPException(status_code=400, detail="Unsupported save target")

    content = payload.content if isinstance(payload.content, str) else ""
    backups: dict[str, str] = {}
    system_command = ""

    if target in {"system", "both"}:
        current_system, _ = _read_system_crontab(safe_user)
        backups["system"] = _create_settings_backup(
            f"crontab_system_{safe_user}",
            f"crontab_system_{safe_user}.txt",
            current_system,
        )
        system_command = _write_system_crontab(safe_user, content)
        # Keep snapshot aligned with the latest applied system crontab.
        _write_crontab_snapshot(safe_user, content)

    if target in {"snapshot", "both"}:
        current_snapshot = _read_crontab_snapshot(safe_user)
        backups["snapshot"] = _create_settings_backup(
            f"crontab_snapshot_{safe_user}",
            f"crontab_snapshot_{safe_user}.txt",
            current_snapshot,
        )
        _write_crontab_snapshot(safe_user, content)

    snapshot_path = _crontab_snapshot_path(safe_user)
    rel_path = snapshot_path.relative_to(_WORKSPACE_ROOT).as_posix() if _WORKSPACE_ROOT in snapshot_path.parents else snapshot_path.as_posix()
    return {
        "success": True,
        "user": safe_user,
        "target": target,
        "saved": True,
        "backups": backups,
        "snapshot_path": rel_path,
        "system_command": system_command,
        "timestamp": int(time.time()),
    }


@app.get("/api/stack/run-cycles", include_in_schema=False)
async def api_stack_run_cycles(limit: int = Query(default=8, ge=1, le=50)) -> dict[str, Any]:
    cron_state = _REPORTS_DIR / ".cron_state"
    if not cron_state.exists() or not cron_state.is_dir():
        return {"success": True, "runs": []}

    run_logs = sorted(
        cron_state.glob("run_*.log"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:limit]

    rows: list[dict[str, Any]] = []
    run_name_re = re.compile(r"^run_(\d+)\.log$", re.IGNORECASE)
    for run_log in run_logs:
        rel = run_log.relative_to(_REPORTS_DIR).as_posix()
        filename = run_log.name
        match = run_name_re.match(filename)
        cycle_no = int(match.group(1)) if match else None
        rows.append(
            {
                "name": filename,
                "cycle": cycle_no,
                "href": _reports_view_link(rel, tail=True, latest=200, refresh=5),
            }
        )

    return {"success": True, "runs": rows}


@app.get("/reports/list", include_in_schema=False)
async def reports_list(path: str = Query(default="")) -> HTMLResponse:
    target = _resolve_reports_path(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    if not target.is_dir():
        rel = target.relative_to(_REPORTS_DIR).as_posix()
        return RedirectResponse(url=_reports_link(rel))

    entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    rows = []
    rel_dir = target.relative_to(_REPORTS_DIR).as_posix() if target != _REPORTS_DIR else ""

    if target != _REPORTS_DIR:
        parent_rel = target.parent.relative_to(_REPORTS_DIR).as_posix()
        rows.append(f"<li><a href='/reports/list?path={quote(parent_rel)}'>../</a></li>")

    for entry in entries:
        rel = entry.relative_to(_REPORTS_DIR).as_posix()
        if entry.is_dir():
            rows.append(f"<li>[DIR] <a href='/reports/list?path={quote(rel)}'>{rel}/</a></li>")
        else:
            is_log = rel.lower().endswith('.log')
            view_url = _reports_view_link(rel, tail=is_log, latest=200, refresh=5 if is_log else 0)
            tail_hint = " <span style='color:#6a7480; font-size:11px;'>(tail 5s)</span>" if is_log else ""
            extra_view_link = f" | <a href='{view_url}'>open tail</a>" if is_log else ""
            rows.append(
                f"<li>[FILE] <a href='{view_url}'>{rel}</a>{tail_hint}"
                f" <span style='color:#6a7480'>(<a href='{_reports_link(rel)}'>raw</a>{extra_view_link})</span></li>"
            )

    body = "".join(rows) if rows else "<li>empty</li>"
    html = f"""
<html><head><title>reports/{rel_dir}</title></head>
<body style='font-family: ui-monospace, monospace; background:#07090c; color:#d7dde4; padding:14px;'>
  <div><a style='color:#ffb000' href='/ui/reports'>[back to UI/reports]</a></div>
  <h3>reports/{rel_dir}</h3>
    <div style='margin:6px 0 10px 0; color:#6a7480;'>Tip: opening any <code>.log</code> file enters auto-refreshing tail mode (5s).</div>
  <ul>{body}</ul>
</body></html>
"""
    return HTMLResponse(content=html)


@app.get("/reports/match", include_in_schema=False)
async def reports_match(
    pattern: str = Query(..., min_length=1),
    latest: int = Query(default=0, ge=0, le=500),
) -> HTMLResponse:
    # Keep matching constrained to the reports root and cap output.
    if pattern.startswith("/") or ".." in pattern:
        raise HTTPException(status_code=400, detail="Invalid match pattern")
    matches = sorted(_REPORTS_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)[:200]
    if latest > 0:
        matches = matches[:latest]

    rows = []
    sev_re = re.compile(r"error|timeout|confirmation_required", re.IGNORECASE)
    for match in matches:
        if not match.is_file():
            continue
        rel = match.relative_to(_REPORTS_DIR).as_posix()
        is_log = rel.lower().endswith('.log')
        view_url = _reports_view_link(rel, tail=is_log, latest=200, refresh=5 if is_log else 0)
        extra_view_link = f" | <a href='{view_url}'>open tail</a>" if is_log else ""
        alert_badge = ""
        if is_log:
            try:
                text = match.read_text(encoding="utf-8", errors="replace")
                alert_hits = len(sev_re.findall(text))
                badge_bg = "rgba(255,176,0,0.18)" if alert_hits > 0 else "rgba(106,116,128,0.14)"
                badge_fg = "#ffb000" if alert_hits > 0 else "#6a7480"
                alert_badge = (
                    f" <span title='error|timeout|confirmation_required hits' "
                    f"style='border:1px solid #1f2630; padding:1px 6px; margin-left:6px; "
                    f"background:{badge_bg}; color:{badge_fg}; border-radius:2px; font-size:11px;'>"
                    f"alerts:{alert_hits}</span>"
                )
            except Exception:
                alert_badge = " <span style='color:#6a7480; margin-left:6px; font-size:11px;'>(alerts:n/a)</span>"

        rows.append(
            f"<li><a href='{view_url}'>{rel}</a>"
            f" <span style='color:#6a7480'>(<a href='{_reports_link(rel)}'>raw</a>{extra_view_link})</span>{alert_badge}</li>"
        )

    body = "".join(rows) if rows else "<li>no matches</li>"
    latest_mode = f"latest={latest}" if latest > 0 else "latest=all"
    latest20_url = f"/reports/match?pattern={quote(pattern)}&latest=20"
    all_url = f"/reports/match?pattern={quote(pattern)}&latest=0"

    html = f"""
<html><head><title>reports match</title></head>
<body style='font-family: ui-monospace, monospace; background:#07090c; color:#d7dde4; padding:14px;'>
  <div><a style='color:#ffb000' href='/ui/reports'>[back to UI/reports]</a></div>
  <h3>Pattern: {pattern}</h3>
  <div style='margin:8px 0 10px 0; color:#6a7480;'>
    mode: {latest_mode} |
    <a style='color:#9ecbff' href='{latest20_url}'>Latest 20</a> |
    <a style='color:#9ecbff' href='{all_url}'>Show up to 200</a>
  </div>
    <div style='margin:0 0 10px 0; color:#6a7480;'>Tip: clicking any <code>.log</code> match opens auto-refreshing tail mode (5s).</div>
  <ul>{body}</ul>
</body></html>
"""
    return HTMLResponse(content=html)


@app.get("/reports/view/{report_path:path}", include_in_schema=False)
async def reports_view(
        report_path: str,
        tail: int = Query(default=0, ge=0, le=1),
        latest: int = Query(default=200, ge=1, le=2000),
        refresh: int = Query(default=0, ge=0, le=60),
    alerts_only: int = Query(default=0, ge=0, le=1),
) -> HTMLResponse:
    target = _resolve_reports_path(report_path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Report file not found")

    raw_text = target.read_text(encoding="utf-8", errors="replace")
    lines = raw_text.splitlines()
    if tail == 1:
        lines = lines[-latest:]
    rel = target.relative_to(_REPORTS_DIR).as_posix()

    sev_re = re.compile(r"error|timeout|confirmation_required", re.IGNORECASE)
    rendered = []
    alert_count = 0
    for idx, line in enumerate(lines, start=1):
        rendered_line = _render_reports_markdown_line(line, rel)
        is_alert = bool(sev_re.search(line))
        if is_alert:
            alert_count += 1
            rendered.append(f"<span class='line sev'>{idx:05d}: {rendered_line}</span>")
        else:
            if alerts_only == 1:
                continue
            rendered.append(f"<span class='line'>{idx:05d}: {rendered_line}</span>")

    tail_mode = "on" if tail == 1 else "off"
    refresh_mode = f"{refresh}s" if refresh > 0 else "off"
    refresh_meta = f"<meta http-equiv='refresh' content='{refresh}'>" if refresh > 0 else ""
    tail_on_url = _reports_view_link(rel, tail=True, latest=latest, refresh=5)
    tail_off_url = _reports_view_link(rel, tail=False, latest=latest, refresh=0)
    latest20_url = _reports_view_link(rel, tail=True, latest=20, refresh=5)
    latest100_url = _reports_view_link(rel, tail=True, latest=100, refresh=5)
    latest500_url = _reports_view_link(rel, tail=True, latest=500, refresh=5)
    alerts_on_url = f"/reports/view/{quote(rel)}?tail={tail}&latest={latest}&refresh={refresh}&alerts_only=1"
    alerts_off_url = f"/reports/view/{quote(rel)}?tail={tail}&latest={latest}&refresh={refresh}&alerts_only=0"
    raw_url = _reports_link(rel)
    alerts_mode = "on" if alerts_only == 1 else "off"

    html_doc = f"""
<html>
    <head>
        <title>report view: {rel}</title>
        {refresh_meta}
        <style>
            body {{ margin:0; padding:14px; background:#07090c; color:#d7dde4; font-family: ui-monospace, monospace; }}
            a {{ color:#9ecbff; text-decoration:none; }}
            a:hover {{ color:#ffb000; text-decoration:underline; }}
            .muted {{ color:#6a7480; }}
            .toolbar {{ margin: 8px 0 10px 0; display:flex; flex-wrap:wrap; gap:8px; align-items:center; }}
            .toolbar a {{ border:1px solid #1f2630; padding:2px 6px; background:#0d1117; }}
            .log {{ white-space:pre-wrap; border:1px solid #1f2630; background:#0d1117; padding:10px; max-height:78vh; overflow:auto; }}
            .line {{ display:block; color:#d7dde4; }}
            .line.sev {{ color:#ffb000; background: rgba(255, 176, 0, 0.08); }}
        </style>
    </head>
    <body>
        <div><a href='/ui/reports'>[back to UI/reports]</a></div>
        <h3 style='margin:8px 0;'>report: {rel}</h3>
        <div class='muted'>tail: {tail_mode} | latest: {latest} | auto-refresh: {refresh_mode} | alerts-only: {alerts_mode} | matched alerts: {alert_count}</div>
        <div class='toolbar'>
            <a href='{tail_on_url}'>Tail ON (5s)</a>
            <a href='{tail_off_url}'>Tail OFF</a>
            <a href='{latest20_url}'>Latest 20</a>
            <a href='{latest100_url}'>Latest 100</a>
            <a href='{latest500_url}'>Latest 500</a>
            <a href='{alerts_on_url}'>Alerts only ON</a>
            <a href='{alerts_off_url}'>Alerts only OFF</a>
            <a href='{raw_url}'>Raw file</a>
        </div>
        <div class='log'>{''.join(rendered) if rendered else '<span class="muted">(empty file)</span>'}</div>
    </body>
</html>
"""
    return HTMLResponse(content=html_doc)


@app.get("/reports/file/{report_path:path}", include_in_schema=False)
async def reports_file(report_path: str) -> FileResponse:
    target = _resolve_reports_path(report_path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Report file not found")
    return FileResponse(path=target)


@app.get("/api/prompt-engineering/config")
async def get_prompt_engineering_config() -> dict[str, Any]:
    script_text = _load_prompt_engineering_script()
    payload = _extract_prompt_engineering_config(script_text)
    payload["success"] = True
    payload["updated_at"] = int(time.time())
    return payload


@app.post("/api/prompt-engineering/financial-strategy/upload")
async def upload_financial_strategy(file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    if not file.filename.lower().endswith(".md"):
        raise HTTPException(status_code=400, detail="Only .md files are supported")

    strategies_dir = (_DOCS_DIR / "strategies").resolve()
    strategies_dir.mkdir(parents=True, exist_ok=True)

    safe_name = Path(file.filename).name
    if not safe_name.endswith(".md"):
        safe_name = f"{safe_name}.md"

    target_path = strategies_dir / safe_name
    if target_path.exists():
        target_path.unlink()

    contents = await file.read()
    target_path.write_bytes(contents)

    relative_path = target_path.relative_to(_DOCS_DIR).as_posix()
    return {
        "success": True,
        "saved": True,
        "path": relative_path,
        "absolute_path": str(target_path),
    }


@app.post("/api/prompt-engineering/config")
async def save_prompt_engineering_config(request: PromptEngineeringSaveRequest) -> dict[str, Any]:
    script_path = _WATCHLIST_RUNNER_SCRIPT
    script_text = _load_prompt_engineering_script()
    current = _extract_prompt_engineering_config(script_text)
    known_params = {row["name"] for row in current["params"]}

    requested_params = request.params or {}
    invalid_keys = [key for key in requested_params if key not in known_params]
    if invalid_keys:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown script parameters: {', '.join(sorted(invalid_keys))}",
        )

    updated_text = script_text
    params_updated = 0
    for key, value in requested_params.items():
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            raise HTTPException(status_code=400, detail=f"Invalid parameter name: {key}")

        clean_value = str(value)
        if "\n" in clean_value or "\r" in clean_value or "}" in clean_value:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid value for {key}: newline and '}}' are not allowed",
            )

        escaped_value = _escape_bash_double_quoted(clean_value)
        line_re = re.compile(
            rf'^(?P<head>[ \t]*{re.escape(key)}="\$\{{{re.escape(key)}:-)(?P<default>[^}}]*)(?P<tail>\}}"(?:[ \t]+#.*)?)$',
            re.MULTILINE,
        )
        updated_text, replaced = line_re.subn(
            rf'\g<head>{escaped_value}\g<tail>',
            updated_text,
            count=1,
        )
        if replaced:
            params_updated += 1

    normalized_prompt = _normalize_prompt_input(request.prompt)
    if not normalized_prompt:
        raise HTTPException(status_code=400, detail="PROMPT cannot be empty")
    escaped_prompt = _escape_bash_double_quoted(normalized_prompt)
    updated_text, prompt_replaced = re.subn(
        r'^PROMPT=".*"$',
        f'PROMPT="{escaped_prompt}"',
        updated_text,
        count=1,
        flags=re.MULTILINE,
    )
    if prompt_replaced != 1:
        raise HTTPException(status_code=500, detail="Failed to update PROMPT variable")

    enabled_value = "true" if bool(request.include_financial_strategy) else "false"
    escaped_enabled = _escape_bash_double_quoted(enabled_value)
    updated_text, enabled_replaced = re.subn(
        r'^FINANCIAL_STRATEGY_ENABLED=".*"$',
        f'FINANCIAL_STRATEGY_ENABLED="{escaped_enabled}"',
        updated_text,
        count=1,
        flags=re.MULTILINE,
    )
    if enabled_replaced != 1:
        updated_text = re.sub(
            r'^(PROMPT=".*")$',
            rf'\1\nFINANCIAL_STRATEGY_ENABLED="{escaped_enabled}"',
            updated_text,
            count=1,
            flags=re.MULTILINE,
        )

    selected_strategy_files = []
    if request.financial_strategy_files:
        selected_strategy_files = [item.strip() for item in request.financial_strategy_files if item and item.strip()]
    elif request.financial_strategy_file:
        selected_strategy_files = [item.strip() for item in request.financial_strategy_file.split(",") if item.strip()]

    strategy_file_value = ",".join(selected_strategy_files)
    escaped_strategy_file = _escape_bash_double_quoted(strategy_file_value)
    updated_text, strategy_file_replaced = re.subn(
        r'^FINANCIAL_STRATEGY_FILE=".*"$',
        f'FINANCIAL_STRATEGY_FILE="{escaped_strategy_file}"',
        updated_text,
        count=1,
        flags=re.MULTILINE,
    )
    if strategy_file_replaced != 1:
        updated_text = re.sub(
            r'^(FINANCIAL_STRATEGY_ENABLED=".*")$',
            rf'\1\nFINANCIAL_STRATEGY_FILE="{escaped_strategy_file}"',
            updated_text,
            count=1,
            flags=re.MULTILINE,
        )

    script_path.write_text(updated_text, encoding="utf-8")
    reloaded = _extract_prompt_engineering_config(script_path.read_text(encoding="utf-8", errors="replace"))

    return {
        "success": True,
        "saved": True,
        "params_updated": params_updated,
        "prompt_updated": True,
        "prompt": reloaded["prompt"],
        "params": reloaded["params"],
        "script_path": str(script_path),
        "updated_at": int(time.time()),
        "financial_strategy_file": reloaded.get("financial_strategy_file", ""),
        "financial_strategy_files": reloaded.get("financial_strategy_files", []),
    }


# ============================================================================
# Pydantic Models
# ============================================================================


class StockAnalysisRequest(BaseModel):
    ticker: str
    force_retrain: bool = False


class WatchListAddRequest(BaseModel):
    ticker: str
    name: Optional[str] = None
    notes: str = ""


class WatchListResponse(BaseModel):
    ticker: str
    name: Optional[str]
    notes: str
    added_at: str



class TradingOrderRequest(BaseModel):
    ticker: str
    side: str  # "buy" or "sell"
    qty: float = 1.0  # quantity of shares


class TradingGuardrailsUpdateRequest(BaseModel):
    max_notional_usd: float


class SellAllPositionsRequest(BaseModel):
    confirm: bool = True


ALPACA_MCP_URL = "http://alpaca-mcp:3001"
DOCKER_SOCKET_PATH = os.getenv("DOCKER_SOCKET_PATH", "/var/run/docker.sock")
STACK_ENV_FILE = os.getenv("STACK_ENV_FILE", "/workspace/.env")
ALPACA_CONTAINER_NAME = os.getenv("ALPACA_MCP_CONTAINER_NAME", "alpaca-mcp")
PORTFOLIO_TREND_BARS_LIMIT = 24


def _floor_qty(qty: float, decimals: int = 4) -> float:
    factor = 10 ** decimals
    return math.floor(float(qty) * factor) / factor


def _compute_guardrail_max_qty(symbol: str, side: str) -> Optional[float]:
    """Compute max executable qty from current guardrails/quote/position.

    Returns None when the cap cannot be computed (e.g. quote unavailable).
    """
    try:
        health_data = _alpaca_mcp_health()
        guardrails = health_data.get("guardrails") or {}
        max_notional = guardrails.get("max_notional_usd")
        if not isinstance(max_notional, (int, float)) or max_notional <= 0:
            return None

        quote = _alpaca_mcp_call("quote_latest", {"symbol": symbol.upper()})
        ask_price = quote.get("ask_price")
        bid_price = quote.get("bid_price")
        side_lc = side.lower()

        if side_lc == "buy":
            remaining_buy_notional = guardrails.get("remaining_buy_notional_usd")
            if isinstance(remaining_buy_notional, (int, float)) and remaining_buy_notional <= 0:
                return 0.0
            effective_notional = (
                float(remaining_buy_notional)
                if isinstance(remaining_buy_notional, (int, float)) and remaining_buy_notional > 0
                else float(max_notional)
            )
            reference_price = ask_price if isinstance(ask_price, (int, float)) and ask_price > 0 else bid_price
            if not isinstance(reference_price, (int, float)) or reference_price <= 0:
                return None
            return _floor_qty(effective_notional / float(reference_price))

        reference_price = bid_price if isinstance(bid_price, (int, float)) and bid_price > 0 else ask_price
        if not isinstance(reference_price, (int, float)) or reference_price <= 0:
            return None

        max_sell_by_notional = _floor_qty(float(max_notional) / float(reference_price))
        position_qty = _alpaca_position_qty(symbol.upper())
        if not isinstance(position_qty, (int, float)):
            return max_sell_by_notional
        return min(max_sell_by_notional, _floor_qty(float(position_qty)))
    except Exception:
        return None


def _alpaca_mcp_post(payload: dict[str, Any], x_confirm: bool = False) -> requests.Response:
    headers = {"Content-Type": "application/json"}
    if x_confirm:
        headers["X-Confirm"] = "true"
    return requests.post(
        f"{ALPACA_MCP_URL}/mcp",
        json=payload,
        headers=headers,
        timeout=10,
    )


def _alpaca_mcp_health() -> dict[str, Any]:
    response = requests.get(f"{ALPACA_MCP_URL}/health", timeout=10)
    response.raise_for_status()
    return response.json()


def _alpaca_mcp_call(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    response = _alpaca_mcp_post(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise HTTPException(status_code=502, detail=_extract_rpc_error(payload, 1))

    content = ((payload.get("result") or {}).get("content") or [])
    for item in content:
        if item.get("type") == "text" and item.get("text"):
            return json.loads(item["text"])
    raise HTTPException(status_code=502, detail="Unexpected Alpaca MCP payload")


def _extract_position_qty(position_payload: Any, symbol: str) -> Optional[float]:
    if isinstance(position_payload, dict):
        if str(position_payload.get("symbol", "")).upper() == symbol:
            raw_qty = position_payload.get("qty")
            if raw_qty is None:
                raw_qty = position_payload.get("qty_available")
            if raw_qty is None:
                return None
            return float(raw_qty)
        return None

    if isinstance(position_payload, list):
        for pos in position_payload:
            qty = _extract_position_qty(pos, symbol)
            if qty is not None:
                return qty
    return None


def _to_optional_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_timestamp_date(value: Any) -> Optional[datetime.date]:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None

    candidates = [raw]
    if raw.endswith("Z"):
        candidates.append(raw[:-1] + "+00:00")

    for item in candidates:
        try:
            parsed = datetime.fromisoformat(item)
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(timezone.utc)
            return parsed.date()
        except Exception:
            continue

    return None


def _records_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("items", "data", "activities", "orders", "results"):
            raw = payload.get(key)
            if isinstance(raw, list):
                return [row for row in raw if isinstance(row, dict)]
    return []


def _fallback_sell_notional_today() -> Optional[float]:
    """Best-effort SELL notional aggregation from activity/order tools.

    Uses the first available source to avoid double-counting records.
    Returns None if no compatible tool/data is available.
    """
    utc_today = datetime.now(timezone.utc).date()
    tool_candidates: list[tuple[str, dict[str, Any]]] = [
        ("activities_list", {"activity_types": "FILL", "direction": "desc", "page_size": 400}),
        ("account_activities", {"activity_types": "FILL", "direction": "desc", "page_size": 400}),
        ("orders_list", {"status": "all", "limit": 400, "direction": "desc"}),
    ]

    for tool_name, arguments in tool_candidates:
        try:
            payload = _alpaca_mcp_call(tool_name, arguments)
        except Exception:
            continue

        rows = _records_from_payload(payload)
        if not rows:
            continue

        total_sell = 0.0
        matched = False
        for row in rows:
            row_date = _parse_timestamp_date(
                row.get("transaction_time")
                or row.get("filled_at")
                or row.get("timestamp")
                or row.get("created_at")
                or row.get("updated_at")
            )
            if row_date is not None and row_date != utc_today:
                continue

            side = str(
                row.get("side")
                or row.get("order_side")
                or row.get("action")
                or row.get("type")
                or ""
            ).strip().lower()
            if side not in {"sell", "s", "sell_short", "sell-long"} and "sell" not in side:
                continue

            qty = _to_optional_float(row.get("qty") or row.get("filled_qty") or row.get("quantity"))
            price = _to_optional_float(
                row.get("price")
                or row.get("filled_avg_price")
                or row.get("avg_fill_price")
                or row.get("avg_price")
                or row.get("execution_price")
            )
            notional = _to_optional_float(
                row.get("notional")
                or row.get("filled_notional")
                or row.get("amount")
                or row.get("net_amount")
                or row.get("gross_amount")
            )
            if notional is None and isinstance(qty, float) and isinstance(price, float):
                notional = qty * price
            if not isinstance(notional, float):
                continue

            matched = True
            total_sell += abs(notional)

        if matched:
            return total_sell

    return None


def _parse_report_session_summary(path: Path) -> Optional[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None

    submitted_at = str(payload.get("submitted_at") or payload.get("timestamp") or "").strip()
    session_date = _parse_timestamp_date(submitted_at)
    if session_date is None:
        try:
            session_date = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).date()
        except Exception:
            return None

    action = str(payload.get("action") or "").strip().lower() or "n/a"
    order_status = str(payload.get("order_status") or "").strip().lower() or "n/a"
    symbol = str(payload.get("symbol") or "").strip().upper() or "-"
    order_id = str(payload.get("order_id") or "").strip() or "-"

    notional = _to_optional_float(payload.get("target_notional"))
    final_qty = _to_optional_float(payload.get("final_qty"))
    current_price = _to_optional_float(payload.get("current_price"))
    if not isinstance(notional, float) and isinstance(final_qty, float) and isinstance(current_price, float):
        notional = abs(final_qty * current_price)

    label = session_date.isoformat()
    if submitted_at:
        label = submitted_at.replace("T", " ")[:16]

    return {
        "kind": "report",
        "label": label,
        "date": session_date.isoformat(),
        "submitted_at": submitted_at or None,
        "symbol": symbol,
        "action": action,
        "status": order_status,
        "order_id": order_id,
        "order_status": order_status,
        "notional": notional,
        "current_price": current_price,
        "final_qty": final_qty,
        "confidence": _to_optional_float(payload.get("confidence")),
        "source": path.name,
    }


def _recent_report_sessions(limit: int = 2) -> list[dict[str, Any]]:
    sessions: list[dict[str, Any]] = []
    candidate_files = sorted(
        _REPORTS_DIR.glob("investment_analysis_cycle_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    for path in candidate_files:
        summary = _parse_report_session_summary(path)
        if not summary:
            continue
        sessions.append(summary)
        if len(sessions) >= limit:
            break

    return sessions


def _fallback_report_notional_today(side: str) -> Optional[float]:
    utc_today = datetime.now(timezone.utc).date()
    normalized_side = str(side or "").strip().lower()
    if normalized_side not in {"buy", "sell"}:
        return None

    total_notional_today = 0.0
    matched_today = False
    by_date_totals: dict[str, float] = {}

    for path in sorted(
        _REPORTS_DIR.glob("investment_analysis_cycle_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    ):
        summary = _parse_report_session_summary(path)
        if not summary:
            continue
        if summary.get("date") != utc_today.isoformat():
            pass
        if str(summary.get("action") or "").lower() != normalized_side:
            continue
        if normalized_side != "sell" and str(summary.get("status") or "").lower() not in {"filled", "partially_filled"}:
            continue

        notional = _to_optional_float(summary.get("notional"))
        if not isinstance(notional, float) or notional <= 0:
            continue

        date_key = str(summary.get("date") or "").strip()
        if date_key:
            by_date_totals[date_key] = by_date_totals.get(date_key, 0.0) + abs(notional)

        if summary.get("date") == utc_today.isoformat():
            matched_today = True
            total_notional_today += abs(notional)

    if matched_today and total_notional_today > 0:
        return total_notional_today

    if by_date_totals:
        latest_date = sorted(by_date_totals.keys(), reverse=True)[0]
        latest_total = by_date_totals.get(latest_date)
        if isinstance(latest_total, float) and latest_total > 0:
            return latest_total

    return None


def _fallback_buy_notional_today() -> Optional[float]:
    return _fallback_report_notional_today("buy")


def _fallback_sell_notional_from_reports_today() -> Optional[float]:
    return _fallback_report_notional_today("sell")


def _latest_completed_report_session_totals() -> tuple[Optional[str], Optional[float], Optional[float]]:
    """Return (session_date, buy_total, sell_total) for latest completed report day.

    Completed means action in {buy,sell} with status in {filled, partially_filled}
    and positive notional value.
    """
    by_date: dict[str, dict[str, float]] = {}

    for path in sorted(
        _REPORTS_DIR.glob("investment_analysis_cycle_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    ):
        summary = _parse_report_session_summary(path)
        if not summary:
            continue

        action = str(summary.get("action") or "").lower()
        status = str(summary.get("status") or "").lower()
        if action not in {"buy", "sell"}:
            continue
        if status not in {"filled", "partially_filled"}:
            continue

        notional = _to_optional_float(summary.get("notional"))
        if not isinstance(notional, float) or notional <= 0:
            continue

        date_key = str(summary.get("date") or "").strip()
        if not date_key:
            continue

        if date_key not in by_date:
            by_date[date_key] = {"buy": 0.0, "sell": 0.0}
        by_date[date_key][action] += abs(notional)

    if not by_date:
        return None, None, None

    latest_date = sorted(by_date.keys(), reverse=True)[0]
    totals = by_date.get(latest_date) or {}
    buy_total = float(totals.get("buy", 0.0))
    sell_total = float(totals.get("sell", 0.0))
    return latest_date, buy_total, sell_total


def _alpaca_position_qty(symbol: str) -> Optional[float]:
    # Prefer single-symbol endpoint if available, then fall back to list.
    for tool_name, args in (
        ("position_get", {"symbol": symbol}),
        ("positions_list", {}),
    ):
        try:
            payload = _alpaca_mcp_call(tool_name, args)
            qty = _extract_position_qty(payload, symbol)
            if qty is not None:
                return qty
            if tool_name == "positions_list" and isinstance(payload, list):
                # Tool is available and returned the open positions list,
                # but this symbol is not present => no open position.
                return 0.0
        except Exception:
            continue
    return None


def _extract_rpc_error(result: dict[str, Any], request_qty: float) -> dict[str, Any]:
    rpc_error = result.get("error") or {}
    detail = rpc_error.get("data") if isinstance(rpc_error.get("data"), dict) else {}
    error_code = detail.get("error") or rpc_error.get("message") or "order_failed"
    message = detail.get("message") or rpc_error.get("message") or "Unknown error"

    parsed = {
        "error": error_code,
        "message": message,
        "code": rpc_error.get("code"),
    }
    for key in ("notional_usd", "max_notional_usd", "orders_today"):
        if key in detail:
            parsed[key] = detail[key]

    notional = detail.get("notional_usd")
    max_notional = detail.get("max_notional_usd")
    if (
        error_code == "max_notional_exceeded"
        and request_qty > 0
        and isinstance(notional, (int, float))
        and isinstance(max_notional, (int, float))
        and notional > 0
        and max_notional > 0
    ):
        estimated_unit_price = float(notional) / float(request_qty)
        parsed["estimated_unit_price"] = estimated_unit_price
        parsed["suggested_qty"] = _floor_qty(float(max_notional) / estimated_unit_price)

    return parsed


def _persist_env_value(key: str, value: str, env_path: str) -> None:
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        lines = []

    replaced = False
    new_lines: list[str] = []
    for line in lines:
        if line.strip().startswith(f"{key}="):
            new_lines.append(f"{key}={value}\n")
            replaced = True
        else:
            new_lines.append(line)

    if not replaced:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] = new_lines[-1] + "\n"
        new_lines.append(f"{key}={value}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def _docker_restart_container(container_name: str) -> None:
    if not os.path.exists(DOCKER_SOCKET_PATH):
        raise HTTPException(
            status_code=500,
            detail=f"Docker socket not available at {DOCKER_SOCKET_PATH}",
        )

    request_bytes = (
        f"POST /containers/{container_name}/restart?t=5 HTTP/1.1\r\n"
        "Host: docker\r\n"
        "Content-Length: 0\r\n"
        "Connection: close\r\n\r\n"
    ).encode("ascii")

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(10)
            sock.connect(DOCKER_SOCKET_PATH)
            sock.sendall(request_bytes)
            response = sock.recv(4096).decode("utf-8", errors="replace")
    except OSError as e:
        raise HTTPException(status_code=502, detail=f"Docker restart failed: {str(e)}")

    status_line = response.splitlines()[0] if response else ""
    status_code = 0
    parts = status_line.split(" ")
    if len(parts) >= 2 and parts[1].isdigit():
        status_code = int(parts[1])
    if status_code not in (204, 304):
        raise HTTPException(
            status_code=502,
            detail=f"Docker restart failed for {container_name}: {status_line or 'no response'}",
        )


def _docker_http_request(method: str, path: str, timeout: int = 10) -> tuple[int, str]:
    if not os.path.exists(DOCKER_SOCKET_PATH):
        raise RuntimeError(f"Docker socket not available at {DOCKER_SOCKET_PATH}")

    request_bytes = (
        f"{method} {path} HTTP/1.1\r\n"
        "Host: docker\r\n"
        "Connection: close\r\n\r\n"
    ).encode("ascii")

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect(DOCKER_SOCKET_PATH)
            sock.sendall(request_bytes)
            chunks: list[bytes] = []
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
    except OSError as e:
        raise RuntimeError(f"Docker request failed: {str(e)}")

    raw = b"".join(chunks)
    header_raw, _, body_raw = raw.partition(b"\r\n\r\n")
    header_text = header_raw.decode("utf-8", errors="replace")

    header_lower = header_text.lower()
    if "transfer-encoding: chunked" in header_lower:
        decoded = bytearray()
        i = 0
        total = len(body_raw)
        while i < total:
            line_end = body_raw.find(b"\r\n", i)
            if line_end == -1:
                break
            size_line = body_raw[i:line_end].split(b";", 1)[0].strip()
            if not size_line:
                break
            try:
                chunk_size = int(size_line.decode("ascii"), 16)
            except Exception:
                break
            i = line_end + 2
            if chunk_size == 0:
                break
            next_i = i + chunk_size
            if next_i > total:
                break
            decoded.extend(body_raw[i:next_i])
            i = next_i + 2
        body_raw = bytes(decoded)

    body_text = body_raw.decode("utf-8", errors="replace")
    status_line = header_text.splitlines()[0] if header_text else ""
    status_code = 0
    parts = status_line.split(" ")
    if len(parts) >= 2 and parts[1].isdigit():
        status_code = int(parts[1])
    return status_code, body_text


def _docker_container_runtime_state(container_name: str) -> dict[str, Any]:
    code, body = _docker_http_request("GET", f"/containers/{container_name}/json")
    if code == 404:
        return {
            "name": container_name,
            "exists": False,
            "running": False,
            "status": "missing",
            "health": None,
            "ok": False,
        }
    if code < 200 or code >= 300:
        raise RuntimeError(f"Docker inspect failed for {container_name}: HTTP {code}")

    payload = json.loads(body) if body else {}
    state = payload.get("State") or {}
    status = str(state.get("Status") or "unknown")
    running = bool(state.get("Running"))
    health_info = state.get("Health") or {}
    health = health_info.get("Status")
    ok = running and (health in (None, "healthy"))

    return {
        "name": container_name,
        "exists": True,
        "running": running,
        "status": status,
        "health": health,
        "ok": ok,
    }


def _docker_job_patch(job_id: str, **kwargs: Any) -> None:
    with _DOCKER_JOB_LOCK:
        if job_id not in _DOCKER_JOBS:
            return
        _DOCKER_JOBS[job_id].update(kwargs)
    _save_docker_jobs_state()


def _docker_job_append_log(job_id: str, line: str) -> None:
    with _DOCKER_JOB_LOCK:
        if job_id not in _DOCKER_JOBS:
            return
        logs = _DOCKER_JOBS[job_id].setdefault("logs", [])
        logs.append(line)
        if len(logs) > 400:
            _DOCKER_JOBS[job_id]["logs"] = logs[-400:]
    _save_docker_jobs_state()


def _resolve_compose_base_command() -> list[str]:
    docker_path = shutil.which("docker")
    if docker_path:
        try:
            check = subprocess.run(
                [docker_path, "compose", "version"],
                cwd=str(_WORKSPACE_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=8,
            )
            if check.returncode == 0:
                return [docker_path, "compose"]
        except Exception:
            pass

    docker_compose_path = shutil.which("docker-compose")
    if docker_compose_path:
        return [docker_compose_path]

    raise RuntimeError("docker compose is not available inside investment-analyst-api container")


def _run_compose_step(
    job_id: str,
    step_label: str,
    cmd: list[str],
    pct_from: int,
    pct_to: int,
    parse_build_progress: bool = False,
) -> None:
    _docker_job_patch(job_id, current_step=step_label, progress=pct_from)
    _docker_job_append_log(job_id, f"$ {' '.join(cmd)}")

    process = subprocess.Popen(
        cmd,
        cwd=str(_WORKSPACE_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    span = max(1, pct_to - pct_from)
    line_counter = 0

    if process.stdout is not None:
        for raw_line in process.stdout:
            line = raw_line.rstrip("\n")
            _docker_job_append_log(job_id, line)
            line_counter += 1

            if parse_build_progress:
                match = re.search(r"\[(\d+)/(\d+)\]", line)
                if match:
                    done = int(match.group(1))
                    total = max(1, int(match.group(2)))
                    progress = pct_from + int((done / total) * span)
                    _docker_job_patch(job_id, progress=min(pct_to - 1, progress))
                    continue

            approx = pct_from + min(span - 1, line_counter)
            _docker_job_patch(job_id, progress=approx)

    exit_code = process.wait()
    if exit_code != 0:
        raise RuntimeError(f"Command failed ({exit_code}): {' '.join(cmd)}")

    _docker_job_patch(job_id, progress=pct_to)


def _docker_action_worker(job_id: str, container_name: str, action: str) -> None:
    started_at = int(time.time())
    _docker_job_patch(job_id, status="running", started_at=started_at, progress=1)

    try:
        compose_base = _resolve_compose_base_command()

        if action == "rebuild_no_cache":
            steps = [
                ("build no-cache", compose_base + ["build", "--no-cache", container_name], 2, 85, True),
                ("up force-recreate", compose_base + ["up", "-d", "--no-deps", "--force-recreate", container_name], 85, 100, False),
            ]
        elif action == "restart":
            steps = [
                ("up force-recreate", compose_base + ["up", "-d", "--no-deps", "--force-recreate", container_name], 2, 100, False),
            ]
        else:
            raise RuntimeError(f"Unsupported action: {action}")

        for label, cmd, pct_from, pct_to, parse_build in steps:
            _run_compose_step(job_id, label, cmd, pct_from, pct_to, parse_build)

        _docker_job_patch(
            job_id,
            status="success",
            progress=100,
            current_step="completed",
            finished_at=int(time.time()),
        )
    except Exception as e:
        _docker_job_append_log(job_id, f"ERROR: {str(e)}")
        _docker_job_patch(
            job_id,
            status="failed",
            error=str(e),
            current_step="failed",
            finished_at=int(time.time()),
        )


def _docker_start_helper_job(job_id: str, action: str) -> None:
    helper_name = f"hb-job-{job_id[:8]}"
    compose_steps: list[str]
    if action == "rebuild_no_cache":
        compose_steps = [
            "docker compose build --no-cache investment-analyst-api",
            "docker compose up -d --no-deps --force-recreate investment-analyst-api",
        ]
    elif action == "restart":
        compose_steps = [
            "docker compose up -d --no-deps --force-recreate investment-analyst-api",
        ]
    else:
        raise RuntimeError(f"Unsupported action: {action}")

    shell_script = "set -e; " + "; ".join(compose_steps)
    cmd = [
        "docker",
        "run",
        "-d",
        "--name",
        helper_name,
        "-v",
        "/var/run/docker.sock:/var/run/docker.sock",
        "-v",
        f"{_WORKSPACE_ROOT}:/workspace",
        "-w",
        "/workspace",
        _DOCKER_HELPER_IMAGE,
        "sh",
        "-lc",
        shell_script,
    ]

    _docker_job_patch(job_id, status="running", progress=8, current_step="delegating", helper_container=helper_name)
    completed = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=25)
    if completed.returncode != 0:
        raise RuntimeError((completed.stdout or "").strip() or "Failed to launch helper container")

    _docker_job_append_log(job_id, f"$ {' '.join(cmd)}")
    _docker_job_append_log(job_id, (completed.stdout or "").strip())
    _docker_job_patch(job_id, progress=15, current_step="helper running")


def _docker_reconcile_helper_job(job: dict[str, Any]) -> dict[str, Any]:
    if job.get("container") != "investment-analyst-api":
        return job
    if job.get("status") not in ("queued", "running"):
        return job

    helper_name = str(job.get("helper_container") or "").strip()
    if not helper_name:
        return job

    try:
        code, body = _docker_http_request("GET", f"/containers/{helper_name}/json")
    except Exception:
        code, body = 0, ""

    now = int(time.time())
    started_at = int(job.get("started_at") or now)
    elapsed = max(0, now - started_at)
    progress = int(job.get("progress") or 0)

    if code == 200:
        payload = json.loads(body) if body else {}
        state = payload.get("State") or {}
        helper_running = bool(state.get("Running"))
        helper_status = str(state.get("Status") or "unknown")
        if helper_running:
            pct = min(95, max(progress, 15 + min(70, elapsed)))
            _docker_job_patch(job["job_id"], progress=pct, current_step=f"helper {helper_status}")
            job.update({"progress": pct, "current_step": f"helper {helper_status}"})
            return job

        exit_code = state.get("ExitCode")
        if exit_code == 0:
            try:
                target = _docker_container_runtime_state("investment-analyst-api")
                if target.get("running") and target.get("health") == "healthy":
                    _docker_job_patch(
                        job["job_id"],
                        status="success",
                        progress=100,
                        current_step="completed",
                        finished_at=int(time.time()),
                    )
                    subprocess.run(["docker", "rm", "-f", helper_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    job.update({"status": "success", "progress": 100, "current_step": "completed"})
                    return job
            except Exception:
                pass

            pct = min(99, max(progress, 85))
            _docker_job_patch(job["job_id"], progress=pct, current_step="waiting for health")
            job.update({"progress": pct, "current_step": "waiting for health"})
            return job

        _docker_job_patch(
            job["job_id"],
            status="failed",
            current_step="failed",
            error=f"helper exited with code {exit_code}",
            finished_at=int(time.time()),
        )
        job.update({"status": "failed", "current_step": "failed", "error": f"helper exited with code {exit_code}"})
        return job

    if code == 404:
        try:
            target = _docker_container_runtime_state("investment-analyst-api")
            if target.get("running") and target.get("health") == "healthy":
                _docker_job_patch(
                    job["job_id"],
                    status="success",
                    progress=100,
                    current_step="completed",
                    finished_at=int(time.time()),
                )
                job.update({"status": "success", "progress": 100, "current_step": "completed"})
                return job
        except Exception:
            pass

        pct = min(99, max(progress, 85))
        _docker_job_patch(job["job_id"], progress=pct, current_step="waiting for health")
        job.update({"progress": pct, "current_step": "waiting for health"})

    return job


def _docker_active_jobs_by_container() -> dict[str, dict[str, Any]]:
    with _DOCKER_JOB_LOCK:
        snapshots = [dict(item) for item in _DOCKER_JOBS.values() if isinstance(item, dict)]

    active_by_container: dict[str, dict[str, Any]] = {}
    for snapshot in snapshots:
        container_name = str(snapshot.get("container") or "").strip()
        if not container_name:
            continue
        if snapshot.get("status") not in ("queued", "running"):
            continue

        if container_name == "investment-analyst-api":
            snapshot = _docker_reconcile_helper_job(snapshot)
            if snapshot.get("status") not in ("queued", "running"):
                continue

        existing = active_by_container.get(container_name)
        snapshot_created = int(snapshot.get("created_at") or 0)
        existing_created = int((existing or {}).get("created_at") or 0)
        if existing is None or snapshot_created >= existing_created:
            active_by_container[container_name] = {
                "job_id": snapshot.get("job_id"),
                "container": container_name,
                "action": snapshot.get("action"),
                "status": snapshot.get("status"),
                "progress": snapshot.get("progress"),
                "current_step": snapshot.get("current_step"),
                "created_at": snapshot.get("created_at"),
                "started_at": snapshot.get("started_at"),
                "error": snapshot.get("error"),
            }

    return active_by_container


def _http_service_runtime_state(service_name: str, url: str, timeout: int = 4) -> dict[str, Any]:
    try:
        response = requests.get(url, timeout=timeout)
        ok = response.ok
        status = "up" if ok else f"http_{response.status_code}"
        health = "healthy" if ok else "unhealthy"
        return {
            "name": service_name,
            "exists": None,
            "running": ok,
            "status": status,
            "health": health,
            "ok": ok,
            "source": "http_probe",
        }
    except Exception as e:
        return {
            "name": service_name,
            "exists": None,
            "running": False,
            "status": "down",
            "health": None,
            "ok": False,
            "source": "http_probe",
            "error": str(e),
        }


def _wait_for_alpaca_health(timeout_seconds: int = 40) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            _alpaca_mcp_health()
            return
        except Exception:
            time.sleep(1)
    raise HTTPException(status_code=504, detail="alpaca-mcp did not become healthy after restart")

# ============================================================================
# Health Check
# ============================================================================


@app.get("/health")
async def health():
    """Health check endpoint."""
    configured_source = "demo" if DEMO_MODE else "yahoo"
    last_source = data_fetcher.get_last_data_source()
    last_fetch_at = data_fetcher.get_last_fetch_at()
    last_fetch_error = data_fetcher.get_last_fetch_error()
    return {
        "status": "ok",
        "service": "investment-analyst-api",
        "version": app.version,
        "model_algorithm": MODEL_ALGORITHM,
        "data_source": last_source if last_source != "unknown" else configured_source,
        "configured_data_source": configured_source,
        "last_fetch_at": last_fetch_at,
        "last_fetch_error": last_fetch_error,
        "watchlist_size": len(watchlist_mgr.get_tickers()),
    }


@app.get("/api/stack/services-health", include_in_schema=False)
async def api_stack_services_health() -> dict[str, Any]:
    service_defs = {
        "alpaca_mcp": os.getenv("ALPACA_MCP_CONTAINER_NAME", "alpaca-mcp"),
        "investment_analyst_api": os.getenv("ANALYST_MCP_CONTAINER_NAME", "investment-analyst-api"),
        "hermes": os.getenv("HERMES_CONTAINER_NAME", "hermes"),
    }

    services: dict[str, Any] = {}
    socket_available = os.path.exists(DOCKER_SOCKET_PATH)
    http_fallback_urls = {
        "alpaca_mcp": os.getenv("ALPACA_MCP_HEALTH_URL", "http://alpaca-mcp:3001/health"),
        "investment_analyst_api": os.getenv("ANALYST_API_HEALTH_URL", "http://127.0.0.1:8001/health"),
        "hermes": os.getenv("HERMES_HEALTH_URL", "http://hermes:9119/"),
    }

    for key, container_name in service_defs.items():
        if not socket_available:
            services[key] = _http_service_runtime_state(container_name, http_fallback_urls[key])
            if services[key].get("status") == "down":
                services[key]["status"] = "docker_socket_unavailable"
            continue
        try:
            services[key] = _docker_container_runtime_state(container_name)
        except Exception as e:
            services[key] = _http_service_runtime_state(container_name, http_fallback_urls[key])
            if services[key].get("ok") is not True:
                services[key]["status"] = "error"
                services[key]["inspect_error"] = str(e)

    return {
        "success": True,
        "docker_socket_available": socket_available,
        "services": services,
        "timestamp": int(time.time()),
    }


@app.get("/api/stack/docker-status", include_in_schema=False)
async def api_stack_docker_status() -> dict[str, Any]:
    socket_available = os.path.exists(DOCKER_SOCKET_PATH)
    rows: list[dict[str, Any]] = []
    active_jobs = _docker_active_jobs_by_container()

    for container_name in _CORE_STACK_CONTAINERS:
        if not socket_available:
            rows.append(
                {
                    "name": container_name,
                    "exists": None,
                    "running": False,
                    "status": "docker_socket_unavailable",
                    "health": None,
                    "healthy_running": False,
                }
            )
            continue

        try:
            state = _docker_container_runtime_state(container_name)
            rows.append(
                {
                    "name": state.get("name", container_name),
                    "exists": state.get("exists"),
                    "running": bool(state.get("running")),
                    "status": state.get("status") or "unknown",
                    "health": state.get("health"),
                    "healthy_running": bool(state.get("running")) and state.get("health") == "healthy",
                }
            )
        except Exception as e:
            rows.append(
                {
                    "name": container_name,
                    "exists": None,
                    "running": False,
                    "status": "error",
                    "health": None,
                    "healthy_running": False,
                    "inspect_error": str(e),
                }
            )

    return {
        "success": True,
        "docker_socket_available": socket_available,
        "containers": rows,
        "active_jobs": active_jobs,
        "timestamp": int(time.time()),
    }


@app.get("/api/stack/docker-status/monitoring", include_in_schema=False)
async def api_stack_docker_status_monitoring() -> dict[str, Any]:
    socket_available = os.path.exists(DOCKER_SOCKET_PATH)
    rows: list[dict[str, Any]] = []

    for container_name in _MONITORING_STACK_CONTAINERS:
        if not socket_available:
            rows.append({"name": container_name, "exists": None, "running": False,
                         "status": "docker_socket_unavailable", "health": None, "healthy_running": False})
            continue
        try:
            state = _docker_container_runtime_state(container_name)
            rows.append({"name": state.get("name", container_name), "exists": state.get("exists"),
                         "running": bool(state.get("running")), "status": state.get("status") or "unknown",
                         "health": state.get("health"),
                         "healthy_running": bool(state.get("running")) and state.get("health") in ("healthy", None)})
        except Exception as e:
            rows.append({"name": container_name, "exists": None, "running": False,
                         "status": "error", "health": None, "healthy_running": False, "inspect_error": str(e)})

    return {"success": True, "docker_socket_available": socket_available,
            "containers": rows, "timestamp": int(time.time())}


@app.post("/api/stack/docker-action", include_in_schema=False)
async def api_stack_docker_action(request: DockerActionRequest) -> dict[str, Any]:
    container_name = (request.container or "").strip()
    action = (request.action or "").strip().lower()

    if container_name not in _CORE_STACK_CONTAINERS and container_name not in _MONITORING_STACK_CONTAINERS:
        raise HTTPException(status_code=400, detail="Container is not in the core stack list")
    if action not in ("rebuild_no_cache", "restart"):
        raise HTTPException(status_code=400, detail="Unsupported action")

    active_jobs = _docker_active_jobs_by_container()
    existing_job = active_jobs.get(container_name)
    if existing_job and existing_job.get("job_id"):
        return {
            "success": True,
            "existing_job": True,
            "job_id": existing_job.get("job_id"),
            "container": container_name,
            "action": existing_job.get("action") or action,
            "status": existing_job.get("status") or "running",
            "progress": int(existing_job.get("progress") or 0),
            "current_step": existing_job.get("current_step") or "running",
        }

    with _DOCKER_JOB_LOCK:
        for existing in _DOCKER_JOBS.values():
            if (
                existing.get("container") == container_name
                and existing.get("status") in ("queued", "running")
            ):
                return {
                    "success": True,
                    "existing_job": True,
                    "job_id": existing.get("job_id"),
                    "container": container_name,
                    "action": existing.get("action") or action,
                    "status": existing.get("status") or "running",
                    "progress": int(existing.get("progress") or 0),
                    "current_step": existing.get("current_step") or "running",
                }

        job_id = str(uuid.uuid4())
        _DOCKER_JOBS[job_id] = {
            "job_id": job_id,
            "container": container_name,
            "action": action,
            "status": "queued",
            "progress": 0,
            "current_step": "queued",
            "logs": [],
            "created_at": int(time.time()),
            "started_at": None,
            "finished_at": None,
            "error": None,
        }
    _save_docker_jobs_state()

    if container_name == "investment-analyst-api":
        # Self-restart/rebuild must be delegated to a helper container that survives API recycle.
        try:
            _docker_start_helper_job(job_id, action)
        except Exception as e:
            _docker_job_patch(
                job_id,
                status="failed",
                current_step="failed",
                error=str(e),
                finished_at=int(time.time()),
            )
            raise HTTPException(status_code=500, detail=f"Failed to launch helper job: {str(e)}")
        return {
            "success": True,
            "job_id": job_id,
            "container": container_name,
            "action": action,
            "status": "running",
            "progress": 15,
        }

    worker = threading.Thread(
        target=_docker_action_worker,
        args=(job_id, container_name, action),
        daemon=True,
    )
    worker.start()

    return {
        "success": True,
        "job_id": job_id,
        "container": container_name,
        "action": action,
        "status": "queued",
        "progress": 0,
    }


@app.get("/api/stack/docker-action/{job_id}", include_in_schema=False)
async def api_stack_docker_action_status(job_id: str) -> dict[str, Any]:
    with _DOCKER_JOB_LOCK:
        job = _DOCKER_JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        snapshot = dict(job)
    snapshot = _docker_reconcile_helper_job(snapshot)
    return {"success": True, "job": snapshot}


@app.get("/api/stack/ollama-curl", include_in_schema=False)
async def api_stack_ollama_curl(timeout_seconds: int = Query(default=6, ge=1, le=20)) -> dict[str, Any]:
    candidate_bases: list[str] = []
    for raw in (
        os.getenv("OLLAMA_BASE_IP"),
        os.getenv("OLLAMA_BASE_URL"),
        os.getenv("OLLAMA_HOST"),
        "http://host.docker.internal:11434",
        "http://ollama:11434",
        "http://127.0.0.1:11434",
    ):
        if not raw:
            continue
        base = raw.strip()
        if not base.startswith(("http://", "https://")):
            base = f"http://{base}:11434"
        base = base.rstrip("/")
        if base not in candidate_bases:
            candidate_bases.append(base)

    if not candidate_bases:
        candidate_bases = ["http://127.0.0.1:11434"]

    errors: list[str] = []
    for base_url in candidate_bases:
        probe_url = f"{base_url}/api/tags"
        started = time.time()
        try:
            response = requests.get(probe_url, timeout=timeout_seconds)
            latency_ms = int((time.time() - started) * 1000)
            status_code = int(response.status_code)

            model_count = None
            model_names: list[str] = []
            payload = None
            try:
                payload = response.json()
            except Exception:
                payload = None

            if isinstance(payload, dict):
                models = payload.get("models")
                if isinstance(models, list):
                    model_count = len(models)
                    for item in models[:8]:
                        if isinstance(item, dict):
                            name = item.get("name") or item.get("model")
                            if isinstance(name, str) and name.strip():
                                model_names.append(name.strip())

            return {
                "success": True,
                "ok": bool(response.ok),
                "base_url": base_url,
                "probe_url": probe_url,
                "curl": f"curl -fsS {probe_url}",
                "status_code": status_code,
                "latency_ms": latency_ms,
                "model_count": model_count,
                "models": model_names,
                "tested_bases": candidate_bases,
                "timestamp": int(time.time()),
            }
        except Exception as e:
            errors.append(f"{base_url}: {e}")

    fallback_base = candidate_bases[0]
    fallback_probe = f"{fallback_base}/api/tags"
    return {
        "success": True,
        "ok": False,
        "base_url": fallback_base,
        "probe_url": fallback_probe,
        "curl": f"curl -fsS {fallback_probe}",
        "status_code": None,
        "latency_ms": None,
        "model_count": None,
        "models": [],
        "tested_bases": candidate_bases,
        "error": "; ".join(errors),
        "timestamp": int(time.time()),
    }


@app.get("/api/settings/files", include_in_schema=False)
async def api_settings_files() -> dict[str, Any]:
    specs = _settings_file_specs()
    files: list[dict[str, Any]] = []
    for key, spec in specs.items():
        kind = spec.get("kind", "local")
        exists = None
        if kind == "local":
            exists = _ensure_workspace_local_path(spec["path"]).exists()
        files.append(
            {
                "key": key,
                "label": spec.get("label", key),
                "kind": kind,
                "path": spec.get("path", ""),
                "exists": exists,
                "editable": True,
            }
        )

    return {
        "success": True,
        "files": files,
        "timestamp": int(time.time()),
    }


@app.get("/api/settings/file", include_in_schema=False)
async def api_settings_file(key: str) -> dict[str, Any]:
    specs = _settings_file_specs()
    spec = specs.get((key or "").strip())
    if not spec:
        raise HTTPException(status_code=404, detail="Unknown settings file key")

    kind = spec.get("kind", "local")
    if kind == "local":
        content = _read_local_settings_file(spec["path"])
    elif kind == "hermes":
        content = _read_hermes_settings_file(spec["path"])
    else:
        raise HTTPException(status_code=500, detail="Unsupported settings file type")

    return {
        "success": True,
        "key": key,
        "label": spec.get("label", key),
        "path": spec.get("path", ""),
        "kind": kind,
        "content": content,
        "timestamp": int(time.time()),
    }


@app.post("/api/settings/file-diff", include_in_schema=False)
async def api_settings_file_diff(payload: SettingsFileDiffRequest) -> dict[str, Any]:
    specs = _settings_file_specs()
    key = (payload.key or "").strip()
    spec = specs.get(key)
    if not spec:
        raise HTTPException(status_code=404, detail="Unknown settings file key")

    kind = spec.get("kind", "local")
    if kind == "local":
        current_content = _read_local_settings_file(spec["path"])
    elif kind == "hermes":
        current_content = _read_hermes_settings_file(spec["path"])
    else:
        raise HTTPException(status_code=500, detail="Unsupported settings file type")

    edited_content = payload.content if isinstance(payload.content, str) else ""
    diff_text = _settings_file_diff_text(spec.get("label", key), current_content, edited_content)

    return {
        "success": True,
        "key": key,
        "label": spec.get("label", key),
        "path": spec.get("path", ""),
        "kind": kind,
        "changed": current_content != edited_content,
        "diff": diff_text,
        "timestamp": int(time.time()),
    }


@app.post("/api/settings/file", include_in_schema=False)
async def api_settings_file_save(payload: SettingsFileSaveRequest) -> dict[str, Any]:
    specs = _settings_file_specs()
    key = (payload.key or "").strip()
    spec = specs.get(key)
    if not spec:
        raise HTTPException(status_code=404, detail="Unknown settings file key")

    kind = spec.get("kind", "local")
    content = payload.content if isinstance(payload.content, str) else ""
    label = spec.get("label", key)

    if kind == "local":
        original_content = _read_local_settings_file(spec["path"])
    elif kind == "hermes":
        original_content = _read_hermes_settings_file(spec["path"])
    else:
        raise HTTPException(status_code=500, detail="Unsupported settings file type")

    backup_rel_path = _create_settings_backup(key, label, original_content)

    if kind == "local":
        _write_local_settings_file(spec["path"], content)
    elif kind == "hermes":
        _write_hermes_settings_file(spec["path"], content)
    else:
        raise HTTPException(status_code=500, detail="Unsupported settings file type")

    return {
        "success": True,
        "key": key,
        "label": spec.get("label", key),
        "path": spec.get("path", ""),
        "kind": kind,
        "saved": True,
        "backup_path": backup_rel_path,
        "timestamp": int(time.time()),
    }


@app.get("/api/trading/guardrails")
async def get_trading_guardrails(ticker: Optional[str] = Query(None)):
    """Expose Alpaca MCP guardrails to the WebGUI."""
    try:
        health_data = _alpaca_mcp_health()
        guardrails = health_data.get("guardrails") or {}
        account_data: dict[str, Any] = {}
        try:
            raw_account = _alpaca_mcp_call("account_get", {})
            if isinstance(raw_account, dict):
                account_data = raw_account
        except Exception:
            account_data = {}

        result = {
            "success": True,
            "mode": health_data.get("mode"),
            "max_orders_per_day": guardrails.get("max_orders_per_day"),
            "max_notional_usd": guardrails.get("max_notional_usd"),
            "remaining_buy_notional_usd": guardrails.get("remaining_buy_notional_usd"),
            "buy_notional_today": guardrails.get("buy_notional_today"),
            "auto_execute": guardrails.get("auto_execute"),
            "orders_today": guardrails.get("orders_today"),
            "persist_supported": os.path.exists(DOCKER_SOCKET_PATH),
            "account_cash": _to_optional_float(account_data.get("cash")),
            "account_buying_power": _to_optional_float(account_data.get("buying_power")),
            "account_equity": _to_optional_float(account_data.get("equity")),
            "account_currency": account_data.get("currency"),
        }
        max_notional = guardrails.get("max_notional_usd")
        if ticker and isinstance(max_notional, (int, float)) and max_notional > 0:
            symbol = ticker.upper()
            quote = _alpaca_mcp_call("quote_latest", {"symbol": symbol})
            ask_price = quote.get("ask_price")
            bid_price = quote.get("bid_price")
            buy_price = ask_price if isinstance(ask_price, (int, float)) and ask_price > 0 else bid_price
            sell_price = bid_price if isinstance(bid_price, (int, float)) and bid_price > 0 else ask_price
            position_qty = _alpaca_position_qty(symbol)

            buy_max_qty = _floor_qty(float(max_notional) / float(buy_price)) if buy_price and buy_price > 0 else 0
            sell_max_qty_by_notional = _floor_qty(float(max_notional) / float(sell_price)) if sell_price and sell_price > 0 else 0
            sell_max_qty_by_position = _floor_qty(position_qty) if isinstance(position_qty, (int, float)) else 0
            sell_max_qty = min(sell_max_qty_by_notional, sell_max_qty_by_position)
            result.update(
                {
                    "ticker": symbol,
                    "buy_estimated_unit_price": buy_price,
                    "sell_estimated_unit_price": sell_price,
                    "position_qty": position_qty,
                    "position_available": isinstance(position_qty, (int, float)),
                    "buy_max_qty": buy_max_qty,
                    "sell_max_qty_by_notional": sell_max_qty_by_notional,
                    "sell_max_qty_by_position": sell_max_qty_by_position,
                    "sell_max_qty": sell_max_qty,
                }
            )
        return result
    except requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=503,
            detail="Cannot reach Alpaca MCP service. Is alpaca-mcp running?",
        )
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Alpaca MCP service timeout")
    except requests.exceptions.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Alpaca MCP health error: {str(e)}")


@app.get("/api/trading/portfolio")
async def get_trading_portfolio() -> dict[str, Any]:
    """Return Alpaca account and open positions snapshot for Portfolio UI."""
    try:
        health_data = _alpaca_mcp_health()
        guardrails = health_data.get("guardrails") if isinstance(health_data, dict) else {}
        if not isinstance(guardrails, dict):
            guardrails = {}

        raw_account = _alpaca_mcp_call("account_get", {})
        account_data = raw_account if isinstance(raw_account, dict) else {}

        raw_positions = _alpaca_mcp_call("positions_list", {})
        positions_payload = raw_positions if isinstance(raw_positions, list) else []

        positions: list[dict[str, Any]] = []
        total_market_value = 0.0
        total_cost_basis = 0.0
        total_unrealized_pl = 0.0

        for item in positions_payload:
            if not isinstance(item, dict):
                continue

            symbol = str(item.get("symbol") or "").upper().strip()
            if not symbol:
                continue

            qty = abs(_to_optional_float(item.get("qty")) or 0.0)
            if qty <= 0:
                continue

            avg_entry_price = _to_optional_float(item.get("avg_entry_price") or item.get("avg_entry"))
            current_price = _to_optional_float(item.get("current_price"))
            market_value = _to_optional_float(item.get("market_value"))
            cost_basis = _to_optional_float(item.get("cost_basis"))
            unrealized_pl = _to_optional_float(item.get("unrealized_pl"))
            unrealized_plpc = _to_optional_float(item.get("unrealized_plpc"))
            unrealized_intraday_pl = _to_optional_float(item.get("unrealized_intraday_pl"))
            unrealized_intraday_plpc = _to_optional_float(item.get("unrealized_intraday_plpc"))

            try:
                quote_data = _alpaca_mcp_call("quote_latest", {"symbol": symbol})
            except Exception:
                quote_data = {}

            ask_price = _to_optional_float(quote_data.get("ask_price"))
            bid_price = _to_optional_float(quote_data.get("bid_price"))

            buy_price = ask_price if isinstance(ask_price, float) and ask_price > 0 else current_price
            sell_price = bid_price if isinstance(bid_price, float) and bid_price > 0 else current_price

            if current_price is None:
                current_price = sell_price or buy_price

            if cost_basis is None and avg_entry_price is not None:
                cost_basis = avg_entry_price * qty
            if market_value is None and current_price is not None:
                market_value = current_price * qty
            if unrealized_pl is None and market_value is not None and cost_basis is not None:
                unrealized_pl = market_value - cost_basis
            if unrealized_plpc is None and unrealized_pl is not None and cost_basis not in (None, 0):
                unrealized_plpc = unrealized_pl / cost_basis

            if market_value is not None:
                total_market_value += market_value
            if cost_basis is not None:
                total_cost_basis += cost_basis
            if unrealized_pl is not None:
                total_unrealized_pl += unrealized_pl

            positions.append(
                {
                    "symbol": symbol,
                    "qty": qty,
                    "side": item.get("side"),
                    "avg_entry_price": avg_entry_price,
                    "current_price": current_price,
                    "buy_price": buy_price,
                    "sell_price": sell_price,
                    "market_value": market_value,
                    "cost_basis": cost_basis,
                    "unrealized_pl": unrealized_pl,
                    "unrealized_plpc": unrealized_plpc,
                    "unrealized_intraday_pl": unrealized_intraday_pl,
                    "unrealized_intraday_plpc": unrealized_intraday_plpc,
                    "exchange": item.get("exchange"),
                }
            )

        positions.sort(
            key=lambda row: row.get("unrealized_pl") if isinstance(row.get("unrealized_pl"), (int, float)) else -1e18,
            reverse=True,
        )

        weighted_unrealized_plpc = None
        if total_cost_basis > 0:
            weighted_unrealized_plpc = total_unrealized_pl / total_cost_basis

        trend_history: dict[str, list[float]] = {}
        for row in positions:
            symbol = str(row.get("symbol") or "").upper().strip()
            if not symbol:
                continue
            try:
                bars_payload = _alpaca_mcp_call(
                    "bars_get",
                    {
                        "symbol": symbol,
                        "timeframe": "1Min",
                        "limit": PORTFOLIO_TREND_BARS_LIMIT,
                    },
                )
            except Exception as e:
                continue

            # Handle multiple response formats from alpaca-mcp
            bars_list = bars_payload
            if isinstance(bars_payload, dict):
                # Format 1: {"symbol": "...", "bars": [...]}
                bars_list = bars_payload.get("bars", [])
            
            if not isinstance(bars_list, list):
                continue

            closes: list[float] = []
            for bar in bars_list:
                if not isinstance(bar, dict):
                    continue
                # Try both "close" and "c" keys (alpaca uses both formats)
                close_value = _to_optional_float(bar.get("close"))
                if close_value is None:
                    close_value = _to_optional_float(bar.get("c"))
                if close_value is None:
                    continue
                closes.append(float(close_value))

            # Store trend data even if short — frontend shows any historical data
            if closes:
                trend_history[symbol] = closes[-PORTFOLIO_TREND_BARS_LIMIT:]

        winner = positions[0] if positions else None
        loser = positions[-1] if positions else None

        account = {
            "cash": _to_optional_float(account_data.get("cash")),
            "buying_power": _to_optional_float(account_data.get("buying_power")),
            "equity": _to_optional_float(account_data.get("equity")),
            "portfolio_value": _to_optional_float(account_data.get("portfolio_value")),
            "last_equity": _to_optional_float(account_data.get("last_equity")),
            "long_market_value": _to_optional_float(account_data.get("long_market_value")),
            "short_market_value": _to_optional_float(account_data.get("short_market_value")),
            "daytrade_count": _to_optional_float(account_data.get("daytrade_count")),
            "status": account_data.get("status"),
            "currency": account_data.get("currency"),
            "multiplier": account_data.get("multiplier"),
        }

        script_text = _load_prompt_engineering_script()
        prompt_cfg = _extract_prompt_engineering_config(script_text)
        selected_strategy_files = prompt_cfg.get("financial_strategy_files")
        if not isinstance(selected_strategy_files, list):
            selected_strategy_files = []

        strategy_enabled = bool(prompt_cfg.get("include_financial_strategy"))
        selected_strategy = selected_strategy_files[0] if selected_strategy_files else ""

        buy_notional_today = _to_optional_float(guardrails.get("buy_notional_today"))
        buy_notional_source = "guardrails" if isinstance(buy_notional_today, float) else None
        sell_notional_today = _to_optional_float(guardrails.get("sell_notional_today"))
        sell_notional_source = "guardrails" if isinstance(sell_notional_today, float) else None
        orders_today = int(guardrails.get("orders_today") or 0)
        has_guardrails_activity = (
            orders_today > 0
            or (isinstance(buy_notional_today, float) and buy_notional_today > 0)
            or (isinstance(sell_notional_today, float) and sell_notional_today > 0)
        )

        session_reference_date = None
        session_reference_mode = "guardrails_today"

        if not has_guardrails_activity:
            session_date, session_buy, session_sell = _latest_completed_report_session_totals()
            if session_date is not None:
                session_reference_date = session_date
                session_reference_mode = "last_completed_session"
                buy_notional_today = session_buy
                sell_notional_today = session_sell
                buy_notional_source = "last_completed_session_report"
                sell_notional_source = "last_completed_session_report"

        day_equity_change = None
        day_equity_change_pct = None
        if isinstance(account["equity"], (int, float)) and isinstance(account["last_equity"], (int, float)):
            day_equity_change = float(account["equity"]) - float(account["last_equity"])
            if float(account["last_equity"]) != 0:
                day_equity_change_pct = day_equity_change / float(account["last_equity"])

        current_session = {
            "kind": "live",
            "label": "Live today",
            "date": datetime.now(timezone.utc).date().isoformat(),
            "submitted_at": int(time.time()),
            "symbol": "portfolio",
            "action": "snapshot",
            "status": "live",
            "order_id": "-",
            "order_status": "live",
            "buy_notional": buy_notional_today,
            "sell_notional": sell_notional_today,
            "net_notional": (
                float(sell_notional_today) - float(buy_notional_today)
                if isinstance(buy_notional_today, float) and isinstance(sell_notional_today, float)
                else None
            ),
            "orders_today": guardrails.get("orders_today"),
            "equity_change": day_equity_change,
            "equity_change_pct": day_equity_change_pct,
            "buy_notional_source": buy_notional_source,
            "sell_notional_source": sell_notional_source,
            "source": "guardrails",
        }

        recent_sessions = _recent_report_sessions(limit=64)
        session_history = [current_session, *recent_sessions]

        return {
            "success": True,
            "mode": health_data.get("mode"),
            "timestamp": int(time.time()),
            "account": account,
            "metrics": {
                "open_positions": len(positions),
                "total_market_value": total_market_value,
                "total_cost_basis": total_cost_basis,
                "total_unrealized_pl": total_unrealized_pl,
                "weighted_unrealized_plpc": weighted_unrealized_plpc,
                "day_equity_change": day_equity_change,
                "day_equity_change_pct": day_equity_change_pct,
                "top_winner_symbol": winner.get("symbol") if winner else None,
                "top_winner_pl": winner.get("unrealized_pl") if winner else None,
                "top_loser_symbol": loser.get("symbol") if loser else None,
                "top_loser_pl": loser.get("unrealized_pl") if loser else None,
            },
            "day_summary": {
                "buy_notional_today": buy_notional_today,
                "buy_notional_source": buy_notional_source,
                "sell_notional_today": sell_notional_today,
                "sell_notional_source": sell_notional_source,
                "orders_today": orders_today,
                "session_reference_mode": session_reference_mode,
                "session_reference_date": session_reference_date,
            },
            "session_history": session_history,
            "financial_strategy": {
                "enabled": strategy_enabled,
                "selected": selected_strategy,
                "selected_all": selected_strategy_files,
            },
            "trend_history": trend_history,
            "positions": positions,
        }
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=503, detail="Cannot reach Alpaca MCP service. Is alpaca-mcp running?")
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Alpaca MCP service timeout")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Portfolio snapshot error: {str(e)}")


@app.post("/api/trading/guardrails")
async def update_trading_guardrails(request: TradingGuardrailsUpdateRequest):
    """Update Alpaca MCP runtime guardrails from the WebGUI."""
    if request.max_notional_usd <= 0:
        raise HTTPException(status_code=400, detail="max_notional_usd must be greater than 0")

    try:
        response = requests.post(
            f"{ALPACA_MCP_URL}/guardrails",
            json={"max_notional_usd": request.max_notional_usd},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        guardrails = payload.get("guardrails") or {}
        return {
            "success": True,
            "max_notional_usd": guardrails.get("max_notional_usd"),
            "remaining_buy_notional_usd": guardrails.get("remaining_buy_notional_usd"),
            "buy_notional_today": guardrails.get("buy_notional_today"),
            "max_orders_per_day": guardrails.get("max_orders_per_day"),
            "auto_execute": guardrails.get("auto_execute"),
            "orders_today": guardrails.get("orders_today"),
            "runtime_only": guardrails.get("runtime_only", True),
        }
    except requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=503,
            detail="Cannot reach Alpaca MCP service. Is alpaca-mcp running?",
        )
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Alpaca MCP service timeout")
    except requests.exceptions.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Alpaca MCP update error: {str(e)}")


@app.post("/api/trading/guardrails/persist")
async def persist_trading_guardrails(request: TradingGuardrailsUpdateRequest):
    """Persist MAX_NOTIONAL_USD to .env and restart alpaca-mcp in one action."""
    if request.max_notional_usd <= 0:
        raise HTTPException(status_code=400, detail="max_notional_usd must be greater than 0")

    try:
        _persist_env_value("MAX_NOTIONAL_USD", str(request.max_notional_usd), STACK_ENV_FILE)
    except PermissionError:
        raise HTTPException(status_code=500, detail=f"Permission denied writing {STACK_ENV_FILE}")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to write {STACK_ENV_FILE}: {str(e)}")

    _docker_restart_container(ALPACA_CONTAINER_NAME)
    _wait_for_alpaca_health()

    # Container restart keeps the existing container config; apply the updated
    # cap at runtime as well so the new value is effective immediately.
    response = requests.post(
        f"{ALPACA_MCP_URL}/guardrails",
        json={"max_notional_usd": request.max_notional_usd},
        headers={"Content-Type": "application/json"},
        timeout=10,
    )
    response.raise_for_status()

    refreshed = await get_trading_guardrails(ticker=None)
    return {
        "success": True,
        "persisted": True,
        "restarted": True,
        "max_notional_usd": refreshed.get("max_notional_usd"),
        "remaining_buy_notional_usd": refreshed.get("remaining_buy_notional_usd"),
        "buy_notional_today": refreshed.get("buy_notional_today"),
        "max_orders_per_day": refreshed.get("max_orders_per_day"),
        "orders_today": refreshed.get("orders_today"),
    }


# ============================================================================
# Time-series endpoint for the dashboard chart
# ============================================================================


@app.get("/api/data/series")
async def fetch_series(
    ticker: str = Query(..., description="Stock ticker symbol"),
    points: int = Query(90, ge=10, le=365, description="Max number of points to return"),
):
    """Return OHLCV time series for the dashboard chart."""
    try:
        df = data_fetcher.fetch_historical_data(ticker, use_cache=True)
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail=f"No data for {ticker}")

        df = df.tail(points)
        records = []
        for idx, row in df.iterrows():
            date_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)
            records.append(
                {
                    "date": date_str,
                    "close": float(row.get("Close", 0) or 0),
                    "volume": float(row.get("Volume", 0) or 0),
                    "high": float(row.get("High", 0) or 0),
                    "low": float(row.get("Low", 0) or 0),
                }
            )
        return {
            "success": True,
            "ticker": ticker.upper(),
            "count": len(records),
            "series": records,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Data Endpoints
# ============================================================================


@app.get("/api/data/fetch")
async def fetch_data(ticker: str = Query(..., description="Stock ticker symbol")):
    """Fetch historical price data for a stock."""
    try:
        df = data_fetcher.fetch_historical_data(ticker, use_cache=True)
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail=f"No data found for {ticker}")

        fundamentals = data_fetcher.fetch_fundamentals(ticker)

        return {
            "success": True,
            "ticker": ticker,
            "data_points": len(df),
            "latest_close": float(df["Close"].iloc[-1]) if "Close" in df.columns else None,
            "fundamentals": fundamentals,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Model Training & Prediction
# ============================================================================


@app.post("/api/model/train")
async def train_model(request: StockAnalysisRequest):
    """Train ML model for a stock."""
    try:
        df = data_fetcher.fetch_historical_data(request.ticker, use_cache=True)
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail=f"No data found for {request.ticker}")

        fundamentals = data_fetcher.fetch_fundamentals(request.ticker)

        result = predictor.train(df, request.ticker, fundamentals)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error"))

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/model/predict")
async def predict_stock(request: StockAnalysisRequest):
    """Get buy/sell/hold prediction for a stock."""
    try:
        # Train model if not exists or force retrain
        if request.force_retrain:
            df = data_fetcher.fetch_historical_data(request.ticker, use_cache=True)
            if df is None or df.empty:
                raise HTTPException(status_code=404, detail=f"No data found for {request.ticker}")

            fundamentals = data_fetcher.fetch_fundamentals(request.ticker)
            train_result = predictor.train(df, request.ticker, fundamentals)
            if not train_result.get("success"):
                raise HTTPException(status_code=400, detail=train_result.get("error"))

        # Get prediction
        df = data_fetcher.fetch_historical_data(request.ticker, use_cache=True)
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail=f"No data found for {request.ticker}")

        fundamentals = data_fetcher.fetch_fundamentals(request.ticker)
        result = predictor.predict(df, request.ticker, fundamentals)

        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error"))

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Watch List Endpoints
# ============================================================================


@app.get("/api/watchlist")
async def get_watchlist():
    """Get current watch list."""
    return watchlist_mgr.get_watchlist()


@app.post("/api/watchlist/add")
async def add_to_watchlist(request: WatchListAddRequest):
    """Add stock to watch list."""
    return watchlist_mgr.add_stock(request.ticker, request.name, request.notes)


@app.get("/api/nasdaq-symbols")
async def get_nasdaq_symbols(
    universe: str = Query("all", description="Symbol universe: all | midcap"),
    q: Optional[str] = Query(None, description="Substring filter, case-insensitive"),
    starts_with: Optional[str] = Query(None, description="Prefix filter, e.g. A, MS"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """Return NASDAQ symbols from docs/NASDAQ_SYMBOLS.md with lightweight filters."""
    universe_key = (universe or "all").strip().lower()
    symbols = _load_nasdaq_symbols(universe_key)

    filtered = symbols
    if starts_with:
        prefix = starts_with.strip().upper()
        filtered = [sym for sym in filtered if sym.startswith(prefix)]
    if q:
        needle = q.strip().upper()
        filtered = [sym for sym in filtered if needle in sym]

    total = len(filtered)
    page = filtered[offset: offset + limit]

    return {
        "success": True,
        "universe": universe_key,
        "available_universes": _available_nasdaq_universes(),
        "total": total,
        "limit": limit,
        "offset": offset,
        "symbols": page,
    }


@app.delete("/api/watchlist/remove")
async def remove_from_watchlist(ticker: str = Query(...)):
    """Remove stock from watch list."""
    return watchlist_mgr.remove_stock(ticker)


@app.delete("/api/watchlist/clear")
async def clear_watchlist():
    """Clear entire watch list."""
    return watchlist_mgr.clear_watchlist()


# ============================================================================
# Analysis Endpoints
# ============================================================================


@app.post("/api/analyze/stock")
async def analyze_stock(request: StockAnalysisRequest):
    """Comprehensive analysis of a single stock."""
    try:
        # Fetch data
        df = data_fetcher.fetch_historical_data(request.ticker, use_cache=True)
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail=f"No data found for {request.ticker}")

        fundamentals = data_fetcher.fetch_fundamentals(request.ticker)

        # Train model
        train_result = predictor.train(df, request.ticker, fundamentals)
        if not train_result.get("success"):
            # If training fails, try prediction anyway (may use cached model)
            pass

        # Get prediction
        pred_result = predictor.predict(df, request.ticker, fundamentals)
        if not pred_result.get("success"):
            raise HTTPException(status_code=400, detail=pred_result.get("error"))

        return {
            "success": True,
            "ticker": request.ticker,
            "training": train_result if train_result.get("success") else None,
            "prediction": pred_result,
            "fundamentals": fundamentals,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/analyze/watchlist")
async def analyze_watchlist(
    force_retrain: bool = Query(
        False,
        description="If true, retrain each ticker's model before predicting (slower).",
    ),
):
    """Analyze all stocks in watch list.

    With `force_retrain=true`, each ticker is retrained on the latest 90 days
    of data before predicting. This is what the dashboard's 60-second
    auto-refresh uses so the watchlist signal always reflects fresh training.
    """
    try:
        tickers = watchlist_mgr.get_tickers()
        if not tickers:
            return {"success": True, "stocks": [], "count": 0, "retrained": 0}

        analyses = []
        retrained = 0
        for ticker in tickers:
            try:
                df = data_fetcher.fetch_historical_data(ticker, use_cache=True)
                if df is None or df.empty:
                    analyses.append({"ticker": ticker, "error": "No data found"})
                    continue

                fundamentals = data_fetcher.fetch_fundamentals(ticker)

                if force_retrain:
                    train_res = predictor.train(df, ticker, fundamentals)
                    if train_res.get("success"):
                        retrained += 1

                pred_result = predictor.predict(df, ticker, fundamentals)

                if pred_result.get("success"):
                    analyses.append(
                        {
                            "ticker": ticker,
                            "action": pred_result.get("action"),
                            "confidence": pred_result.get("confidence"),
                            "price": pred_result.get("latest_price"),
                        }
                    )
                else:
                    analyses.append({"ticker": ticker, "error": "Prediction failed"})
            except Exception as e:
                analyses.append({"ticker": ticker, "error": str(e)})

        return {
            "success": True,
            "stocks": analyses,
            "count": len(analyses),
            "retrained": retrained,
            "recommendations": {
                "buy": len([s for s in analyses if s.get("action") == "BUY"]),
                "sell": len([s for s in analyses if s.get("action") == "SELL"]),
                "hold": len([s for s in analyses if s.get("action") == "HOLD"]),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




# ============================================================================
# Trading Endpoints (Alpaca MCP Integration)
# ============================================================================


@app.post("/api/trading/order")
async def place_trading_order(request: TradingOrderRequest):
    """
    Place a market order via Alpaca.
    Calls alpaca-mcp MCP server to execute order_place_market.
    """
    try:
        # Validate inputs
        side = request.side.lower()
        if side not in ["buy", "sell"]:
            raise HTTPException(status_code=400, detail="side must be 'buy' or 'sell'")

        requested_qty = float(request.qty)
        if requested_qty <= 0:
            raise HTTPException(status_code=400, detail="qty must be greater than 0")

        normalized_qty = _floor_qty(requested_qty)
        if normalized_qty <= 0:
            raise HTTPException(
                status_code=400,
                detail="qty is too small after precision normalization; minimum supported is 0.0001",
            )

        effective_qty = normalized_qty
        max_guardrail_qty = _compute_guardrail_max_qty(request.ticker.upper(), side)
        adjusted_for_guardrails = False
        if not isinstance(max_guardrail_qty, (int, float)) or max_guardrail_qty <= 0:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "max_buy_notional_exceeded" if side == "buy" else "qty_below_guardrail",
                    "message": (
                        "BUY is blocked until the trading limit budget becomes available again."
                        if side == "buy"
                        else "SELL is blocked because no executable quantity is available under the current guardrails.") ,
                    "requested_qty": requested_qty,
                    "normalized_qty": normalized_qty,
                    "max_guardrail_qty": max_guardrail_qty,
                },
            )

        if effective_qty > max_guardrail_qty:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "max_buy_notional_exceeded" if side == "buy" else "qty_below_guardrail",
                    "message": (
                        "Requested BUY exceeds the remaining trading limit budget."
                        if side == "buy"
                        else "Requested qty exceeds the current trading guardrail cap."
                    ),
                    "requested_qty": requested_qty,
                    "normalized_qty": normalized_qty,
                    "max_guardrail_qty": max_guardrail_qty,
                },
            )

        if effective_qty <= 0:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "qty_below_guardrail",
                    "message": "Requested qty exceeds current guardrails and no executable fractional qty is available.",
                    "requested_qty": requested_qty,
                    "normalized_qty": normalized_qty,
                    "max_guardrail_qty": max_guardrail_qty,
                },
            )
        
        # Prepare JSON-RPC 2.0 call to alpaca-mcp
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "order_place_market",
                "arguments": {
                    "symbol": request.ticker.upper(),
                    "qty": effective_qty,
                    "side": side,
                    "time_in_force": "day"
                }
            }
        }

        # Call alpaca-mcp
        response = _alpaca_mcp_post(payload, x_confirm=True)

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Alpaca MCP error: {response.text}"
            )

        result = response.json()

        # Check for JSON-RPC errors
        if "error" in result and result["error"]:
            error_detail = _extract_rpc_error(result, effective_qty)
            status_code = 403 if str(error_detail.get("error", "")).startswith("max_") else 400
            raise HTTPException(
                status_code=status_code,
                detail=error_detail,
            )

        return {
            "success": True,
            "ticker": request.ticker.upper(),
            "side": side,
            "qty": effective_qty,
            "requested_qty": requested_qty,
            "normalized_qty": normalized_qty,
            "adjusted_for_guardrails": adjusted_for_guardrails,
            "max_guardrail_qty": max_guardrail_qty,
            "result": result.get("result", {})
        }
    
    except requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=503,
            detail="Cannot reach Alpaca MCP service. Is alpaca-mcp running?"
        )
    except requests.exceptions.Timeout:
        raise HTTPException(
            status_code=504,
            detail="Alpaca MCP service timeout"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Trading error: {str(e)}")


@app.post("/api/trading/sell-all")
async def sell_all_positions(request: SellAllPositionsRequest):
    if request.confirm is not True:
        raise HTTPException(status_code=400, detail="confirm must be true")

    try:
        positions_payload = _alpaca_mcp_call("positions_list", {})
        positions = positions_payload if isinstance(positions_payload, list) else []

        closeable_symbols: list[str] = []
        for position in positions:
            if not isinstance(position, dict):
                continue
            symbol = str(position.get("symbol") or "").upper().strip()
            if not symbol:
                continue
            try:
                qty_value = abs(float(position.get("qty") or 0))
            except (TypeError, ValueError):
                qty_value = 0.0
            if qty_value > 0:
                closeable_symbols.append(symbol)

        results: list[dict[str, Any]] = []
        for symbol in closeable_symbols:
            response = _alpaca_mcp_post(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "position_close", "arguments": {"symbol": symbol}},
                },
                x_confirm=True,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("error"):
                results.append({"symbol": symbol, "closed": False, "error": _extract_rpc_error(payload, 1)})
            else:
                results.append({"symbol": symbol, "closed": True, "result": payload.get("result", {})})

        closed_count = len([item for item in results if item.get("closed") is True])
        return {
            "success": True,
            "mode": _alpaca_mcp_health().get("mode"),
            "positions_found": len(closeable_symbols),
            "closed_count": closed_count,
            "skipped_count": max(0, len(closeable_symbols) - closed_count),
            "results": results,
        }
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=503, detail="Cannot reach Alpaca MCP service. Is alpaca-mcp running?")
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Alpaca MCP service timeout")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SELL ALL failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
