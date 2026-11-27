# RUNBOOK: Docker Compose Ghost Container Fallback

When `docker compose` fails with:

`Error response from daemon: No such container: <long-id>`

and `docker ps -a` still shows a `Dead` entry for the same id, use this fallback.

## Scope

This runbook is for Honey Barrel stack in:

`/home/me/git-repo/honey-barrel-finale/workspace`

## Symptoms

- `docker compose up -d` fails with `No such container`.
- `docker compose ps -a` fails with the same id.
- `docker ps -a --filter status=dead` shows a dead ghost record.

## Emergency operations (no compose state dependency)

Use the emergency script:

```bash
cd /home/me/git-repo/honey-barrel-finale/workspace
./scripts/hb_stack_emergency.sh status
./scripts/hb_stack_emergency.sh start
./scripts/hb_stack_emergency.sh health
```

Stop sequence:

```bash
./scripts/hb_stack_emergency.sh stop
```

## What the script does

- Starts core containers directly with `docker start`:
  - `workspace`
  - `alpaca-mcp`
  - `workspace-mcp`
  - `stdio-terminal`
  - `mcp-toolbox`
- Detects API container name dynamically:
  - prefers `investment-analyst-api`
  - fallback: any name ending with `investment-analyst-api`
- Starts `hermes` last.
- Runs health checks for:
  - `http://127.0.0.1:18001/health`
  - `http://127.0.0.1:3003/health`
  - `http://127.0.0.1:9119/health`

## Permanent fix (requires root)

```bash
sudo systemctl restart docker
cd /home/me/git-repo/honey-barrel-finale/workspace
docker compose down --remove-orphans
docker compose up -d
docker compose ps -a
```

If root restart is not available, continue with emergency script until maintenance window.
