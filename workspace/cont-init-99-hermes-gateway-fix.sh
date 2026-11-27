#!/bin/sh
mkdir -p /run/s6/container_environment
printf "%s\n" "${HERMES_HOME:-/opt/data}" > /run/s6/container_environment/HERMES_HOME
rm -f /run/hermes-service/gateway-default/down
if [ -d /run/hermes-service/gateway-default ] && [ -x /package/admin/s6/command/s6-svc ]; then
/package/admin/s6/command/s6-svc -u /run/hermes-service/gateway-default 2>/dev/null || true
fi
