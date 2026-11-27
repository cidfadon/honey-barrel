#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────
#  bootstrap-env.sh
#  Interactive .env generator for the Trading212 × OpenClaw stack.
#
#  Usage:   ./scripts/bootstrap-env.sh           (interactive)
#           ./scripts/bootstrap-env.sh --mock    (zero-prompt, mock mode)
#           ./scripts/bootstrap-env.sh --force   (overwrite existing .env)
# ──────────────────────────────────────────────────────────────────────────
set -euo pipefail

# Resolve repo root (script lives in scripts/)
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
TEMPLATE="$ROOT/.env.example"
TARGET="$ROOT/.env"

# ---- args ----------------------------------------------------------------
MODE="interactive"
FORCE=0
for arg in "$@"; do
  case "$arg" in
    --mock)   MODE="mock" ;;
    --force)  FORCE=1 ;;
    -h|--help)
      sed -n '2,11p' "$0"; exit 0 ;;
    *) echo "unknown arg: $arg" >&2; exit 2 ;;
  esac
done

# ---- pre-checks ----------------------------------------------------------
if [[ ! -f "$TEMPLATE" ]]; then
  echo "✗ $TEMPLATE not found — are you running this from inside the repo?" >&2
  exit 1
fi

if [[ -f "$TARGET" && $FORCE -eq 0 ]]; then
  echo "✗ $TARGET already exists. Re-run with --force to overwrite."
  echo "   (or just edit it manually: nano $TARGET)"
  exit 1
fi

# ---- helpers -------------------------------------------------------------
gen_secret() { openssl rand -hex "${1:-24}"; }

ask() {
  # ask "prompt" "default"  -> echoes user value (or default if empty)
  local prompt="$1" default="${2:-}"
  local reply
  if [[ -n "$default" ]]; then
    read -r -p "  $prompt [$default]: " reply
    echo "${reply:-$default}"
  else
    read -r -p "  $prompt: " reply
    echo "$reply"
  fi
}

set_kv() {
  # set_kv KEY VALUE   -> rewrites or appends KEY=VALUE in $TARGET
  local key="$1" val="$2"
  # escape | for sed
  val="${val//|/\\|}"
  if grep -qE "^${key}=" "$TARGET"; then
    sed -i.bak "s|^${key}=.*|${key}=${val}|" "$TARGET" && rm -f "$TARGET.bak"
  else
    echo "${key}=${val}" >> "$TARGET"
  fi
}

# ---- start ---------------------------------------------------------------
cp "$TEMPLATE" "$TARGET"
echo "✓ Created $TARGET from template"
echo

if [[ "$MODE" == "mock" ]]; then
  echo "→ --mock: filling deterministic values, no prompts"
  set_kv T212_MODE         "mock"
  set_kv T212_API_KEY      "not-needed-in-mock"
  set_kv T212_API_SECRET   "not-needed-in-mock"
  set_kv POSTGRES_PASSWORD "$(gen_secret 24)"
  set_kv OPENCLAW_SECRET   "$(gen_secret 32)"
  set_kv AUTO_EXECUTE      "false"
  set_kv ENABLE_GPU        "false"
else
  echo "→ Interactive setup. Press Enter to keep the default in [brackets]."
  echo

  echo "[Trading212]"
  T212_MODE=$(ask "Mode (mock|demo|live)" "mock")
  set_kv T212_MODE "$T212_MODE"

  if [[ "$T212_MODE" == "mock" ]]; then
    set_kv T212_API_KEY    "not-needed-in-mock"
    set_kv T212_API_SECRET "not-needed-in-mock"
  else
    echo "  Generate keys at: https://app.trading212.com → Settings → API → New key"
    set_kv T212_API_KEY    "$(ask "T212_API_KEY")"
    set_kv T212_API_SECRET "$(ask "T212_API_SECRET")"
  fi
  echo

  echo "[Ollama / LLM]"
  set_kv OLLAMA_MODEL "$(ask "OLLAMA_MODEL" "gemma3:4b-it-qat")"
  set_kv ENABLE_GPU  "$(ask "ENABLE_GPU (true|false)" "false")"
  echo

  echo "[PostgreSQL]"
  set_kv POSTGRES_USER     "$(ask "POSTGRES_USER" "t212")"
  set_kv POSTGRES_DB       "$(ask "POSTGRES_DB"   "t212")"
  pw_default="$(gen_secret 24)"
  set_kv POSTGRES_PASSWORD "$(ask "POSTGRES_PASSWORD (Enter = random)" "$pw_default")"
  echo

  echo "[Safety caps]"
  set_kv MAX_ORDERS_PER_DAY "$(ask "MAX_ORDERS_PER_DAY" "5")"
  set_kv MAX_NOTIONAL_EUR   "$(ask "MAX_NOTIONAL_EUR"   "200")"
  ae_default="false"
  [[ "$T212_MODE" == "live" ]] && ae_default="false"
  set_kv AUTO_EXECUTE "$(ask "AUTO_EXECUTE (true|false)" "$ae_default")"
  echo

  echo "[OpenClaw]"
  oc_default="$(gen_secret 32)"
  set_kv OPENCLAW_SECRET "$(ask "OPENCLAW_SECRET (Enter = random)" "$oc_default")"
fi

# ---- sanity --------------------------------------------------------------
echo
echo "──────────────────────────────────────────────────────────────────"
if grep -qE "replace_me|change_me_strong|generate_a_long_random_string" "$TARGET"; then
  echo "⚠ Some placeholder values are still present in $TARGET:"
  grep -nE "replace_me|change_me_strong|generate_a_long_random_string" "$TARGET"
  echo "  → Edit $TARGET manually before running 'make up'."
else
  echo "✓ No placeholder values left. You're good to run:"
  echo "    make demo     # if T212_MODE=mock"
  echo "    make up       # if T212_MODE=demo|live (set ENABLE_GPU=true only on NVIDIA hosts)"
fi
echo "──────────────────────────────────────────────────────────────────"
