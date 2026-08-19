#!/bin/sh
set -eu

TARGET_UID="${HOST_UID:-1000}"
TARGET_GID="${HOST_GID:-1000}"

# Align Hermes runtime UID/GID with host user so files written to bind mounts
# (for example /workspace/reports) are owned by the host account.
if [ "$(id -u hermes)" != "$TARGET_UID" ] || [ "$(id -g hermes)" != "$TARGET_GID" ]; then
	if getent group "$TARGET_GID" >/dev/null 2>&1; then
		usermod -g "$TARGET_GID" hermes || true
	else
		groupmod -g "$TARGET_GID" hermes || true
	fi

	if getent passwd "$TARGET_UID" >/dev/null 2>&1; then
		EXISTING_USER="$(getent passwd "$TARGET_UID" | cut -d: -f1)"
		if [ "$EXISTING_USER" != "hermes" ]; then
			echo "WARN: UID $TARGET_UID already belongs to $EXISTING_USER; keeping hermes UID $(id -u hermes)." >&2
		else
			usermod -u "$TARGET_UID" hermes || true
		fi
	else
		usermod -u "$TARGET_UID" hermes || true
	fi
fi

# Ensure Hermes runtime user can persist custom skills when
# /opt/data/skills is bind-mounted from host with different ownership.
mkdir -p /opt/data/skills
mkdir -p /workspace/reports

# Keep persistent dirs aligned with runtime account after UID/GID remap.
chown -R "$(id -u hermes):$(id -g hermes)" /opt/data /workspace/reports || true

# Persist Ollama endpoint into Hermes config.yaml so it survives container
# recreates and remains visible in /opt/data/config.yaml.
HERMES_BIN="/opt/hermes/.venv/bin/hermes"
if [ -x "$HERMES_BIN" ]; then
	OLLAMA_ENDPOINT="${OLLAMA_BASE_URL:-}"
	if [ -z "$OLLAMA_ENDPOINT" ] && [ -n "${OLLAMA_BASE_IP:-}" ]; then
		OLLAMA_ENDPOINT="http://${OLLAMA_BASE_IP}:11434"
	fi

	if [ -n "$OLLAMA_ENDPOINT" ]; then
		case "$OLLAMA_ENDPOINT" in
			*/v1)
				OLLAMA_ENDPOINT_V1="$OLLAMA_ENDPOINT"
				;;
			*)
				OLLAMA_ENDPOINT_V1="${OLLAMA_ENDPOINT%/}/v1"
				;;
		esac

		"$HERMES_BIN" config set providers.local-ollama.base_url "$OLLAMA_ENDPOINT_V1" >/dev/null 2>&1 || true
		"$HERMES_BIN" config set providers.local-ollama.api_key "dev-local-key-change-me" >/dev/null 2>&1 || true
		"$HERMES_BIN" config set providers.local-ollama.api_mode openai >/dev/null 2>&1 || true
		"$HERMES_BIN" config set model.provider local-ollama >/dev/null 2>&1 || true
		"$HERMES_BIN" config set model.default "${OLLAMA_MODEL:-gemma4-hermes:latest}" >/dev/null 2>&1 || true
		"$HERMES_BIN" config set model.base_url "$OLLAMA_ENDPOINT_V1" >/dev/null 2>&1 || true
		"$HERMES_BIN" config set model.api_key "dev-local-key-change-me" >/dev/null 2>&1 || true
		"$HERMES_BIN" config set auxiliary.vision.base_url "$OLLAMA_ENDPOINT_V1" >/dev/null 2>&1 || true
	fi
fi

# Store explicit OLLAMA_* values in config.yaml for easier diagnostics.
# Keep this block idempotent by replacing a managed marker section.
CONFIG_FILE="/opt/data/config.yaml"
if [ -f "$CONFIG_FILE" ]; then
	TMP_CONFIG="$(mktemp)"
	awk '
		BEGIN {skip_marker=0; skip_env=0}
		{
			if ($0 ~ /^# BEGIN HONEY_BARREL_OLLAMA$/) {skip_marker=1; next}
			if ($0 ~ /^# END HONEY_BARREL_OLLAMA$/) {skip_marker=0; next}
			if (skip_marker) {next}

			if ($0 ~ /^honey_barrel_env:[[:space:]]*$/) {skip_env=1; next}
			if (skip_env) {
				if ($0 ~ /^  /) {next}
				skip_env=0
			}

			print
		}
	' "$CONFIG_FILE" > "$TMP_CONFIG"

	# Drop known empty placeholder keys that Hermes warns about in gateway logs.
	sed -i '/^max_concurrent_sessions:[[:space:]]*null$/d' "$TMP_CONFIG"

	cat >> "$TMP_CONFIG" <<EOF
# BEGIN HONEY_BARREL_OLLAMA
honey_barrel_env:
  OLLAMA_BASE_IP: "${OLLAMA_BASE_IP:-}"
  OLLAMA_BASE_URL: "${OLLAMA_BASE_URL:-}"
  OLLAMA_MODEL: "${OLLAMA_MODEL:-}"
# END HONEY_BARREL_OLLAMA
EOF

	mv "$TMP_CONFIG" "$CONFIG_FILE"
	chown "$(id -u hermes):$(id -g hermes)" "$CONFIG_FILE" || true
fi

# Auto-bootstrap custom investment skills on every start.
# Hermes reads skills from ~/.hermes/skills which is /opt/data/skills
# Do not overwrite user-edited files; only restore missing ones.
for skill in investment-analyst investment-broker investment-analysis-cycle; do
	if [ ! -f "/opt/data/skills/$skill/SKILL.md" ] && [ -f "/usr/local/share/hermes-seed-skills/$skill/SKILL.md" ]; then
		mkdir -p "/opt/data/skills/$skill"
		cp "/usr/local/share/hermes-seed-skills/$skill/SKILL.md" "/opt/data/skills/$skill/SKILL.md"
	fi
done

chmod -R a+rwx /opt/data/skills || true

# Force Hermes to regenerate skill manifest by removing cached bundled_manifest.
# This ensures newly bootstrapped skills are discovered on container start.
rm -f /opt/data/skills/.bundled_manifest

exec /init /opt/hermes/docker/main-wrapper.sh "$@"
