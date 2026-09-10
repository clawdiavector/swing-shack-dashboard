"""
This file exists solely to trigger a Railway image rebuild so we can
verify that the persistent /data volume preserves runtime state across
deploys (P0.5 proof).

The volume MUST outlive the container that this file is baked into.
If after the rebuild the runtime still sees the 4 records we wrote
post-volume-mount, the durability contract holds.

The file is intentionally a no-op module — the app doesn't import it.
"""
REBUILD_TRIGGER = "P0.5-rebuild-test-2026-09-10"
# Second rebuild for P0.5 write-test — 1789020996
