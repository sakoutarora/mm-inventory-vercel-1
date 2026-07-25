#!/usr/bin/env bash
set -euo pipefail

# Clone remote MongoDB to local MongoDB (READ-ONLY on remote)
#
# - mongodump is READ-ONLY: it only exports data from the remote server.
#   Nothing is modified or deleted on the remote.
# - mongorestore --drop only drops collections on the LOCAL target before
#   restoring the dumped data.
#
# Usage: ./scripts/clone-remote-db.sh [remote_uri] [local_uri]

REMOTE_URI="${1:-mongodb://admin:mexicanmama@13.234.226.253:27017/?authSource=admin}"
LOCAL_URI="${2:-mongodb://admin:mexicanmama@localhost:27017/?authSource=admin}"
DB_NAME="inventory"
DUMP_DIR="/tmp/inventory-mongodump"

info()  { echo "▸ $*"; }
ok()    { echo "✓ $*"; }
fail()  { echo "✗ $*" >&2; exit 1; }

# Safety check: make sure restore target is localhost, not the remote
if echo "$LOCAL_URI" | grep -q "13.234.226.253"; then
    fail "LOCAL_URI points to the remote server. Refusing to run to protect remote data."
fi

# Pre-flight
for cmd in mongodump mongorestore; do
    command -v "$cmd" &>/dev/null || fail "$cmd not found. Install with: brew install mongodb-database-tools"
done

echo ""
echo "  Source (READ-ONLY): $REMOTE_URI"
echo "  Target (will drop & restore): $LOCAL_URI"
echo "  Database: $DB_NAME"
echo ""

# Dump from remote (read-only operation)
info "Dumping '$DB_NAME' from remote (read-only, nothing is modified on remote) ..."
rm -rf "$DUMP_DIR"
mongodump \
    --uri="$REMOTE_URI" \
    --db="$DB_NAME" \
    --out="$DUMP_DIR" \
    --quiet

ok "Dump complete ($(du -sh "$DUMP_DIR/$DB_NAME" | awk '{print $1}'))"

# Restore to local (--drop only affects LOCAL collections)
info "Restoring '$DB_NAME' to local (replaces local data only) ..."
mongorestore \
    --uri="$LOCAL_URI" \
    --db="$DB_NAME" \
    --dir="$DUMP_DIR/$DB_NAME" \
    --drop \
    --quiet

ok "Restore complete"

# Cleanup
rm -rf "$DUMP_DIR"
ok "All done - local '$DB_NAME' is now a copy of remote"
