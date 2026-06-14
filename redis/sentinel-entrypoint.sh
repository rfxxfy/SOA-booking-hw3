#!/bin/sh
set -eu

echo "waiting for redis-master DNS..."
MASTER_IP=""
until [ -n "$MASTER_IP" ]; do
  MASTER_IP=$(getent hosts redis-master | awk '{print $1; exit}')
  sleep 1
done
echo "resolved redis-master to $MASTER_IP"

CONF=/tmp/sentinel.conf
cat > "$CONF" <<EOF
port 26379
dir /tmp
sentinel monitor mymaster ${MASTER_IP} 6379 2
sentinel down-after-milliseconds mymaster 5000
sentinel failover-timeout mymaster 10000
sentinel parallel-syncs mymaster 1
EOF

echo "starting sentinel with generated config"
exec redis-sentinel "$CONF"
