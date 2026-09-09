#!/usr/bin/env bash
# Would this commit deploy, and what is still missing?
# Exit 0 = deployable (module gaps reported, not fatal unless STRICT=1).
#   bash tests/smoke_boot.sh
#   STRICT=1 bash tests/smoke_boot.sh
#   SMOKE_URL=https://<service>.up.railway.app bash tests/smoke_boot.sh
#   SMOKE_PORT=3728 bash tests/smoke_boot.sh
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

STRICT="${STRICT:-}"
SMOKE_URL="${SMOKE_URL:-}"
FAIL=0

die() {
  echo "ERROR: $*" >&2
  exit "${2:-1}"
}

preflight() {
  command -v docker >/dev/null || die "docker not on PATH" 3
  command -v curl >/dev/null || die "curl not on PATH" 3
  command -v python3 >/dev/null || die "python3 not on PATH" 3
  test -f Dockerfile || die "Dockerfile missing at repo root" 3
}

static_json() {
  python3 scripts/check_lib_modules.py --json || true
}

print_gap_block() {
  python3 -c '
import json, sys
d = json.load(sys.stdin)
missing = d.get("lib_modules_missing")
present = d.get("lib_modules_present")
if isinstance(present, list):
    present_n = len(present)
elif present is None:
    present_n = "?"
else:
    present_n = present
if missing is None:
    missing_n = "?"
    missing_list = []
elif isinstance(missing, list):
    missing_n = len(missing)
    missing_list = missing
else:
    missing_n = missing
    missing_list = []
print(f"lib_modules_present:    {present_n}")
print(f"lib_modules_missing:    {missing_n}")
if missing_list:
    print("  " + " ".join(missing_list))
sp = d.get("strategy_page_present")
if isinstance(sp, bool):
    print(f"strategy_page_present:  {str(sp).lower()}")
else:
    print(f"strategy_page_present:  {sp}")
'
}

missing_count() {
  python3 -c '
import json, sys
d = json.load(sys.stdin)
m = d.get("lib_modules_missing")
if m is None:
    print(1)
elif isinstance(m, list):
    print(len(m))
else:
    print(1)
'
}

missing_names() {
  python3 -c '
import json, sys
d = json.load(sys.stdin)
m = d.get("lib_modules_missing") or []
print(" ".join(m) if isinstance(m, list) else "")
'
}

pick_port() {
  if [ -n "${SMOKE_PORT:-}" ]; then
    printf '%s' "$SMOKE_PORT"
    return
  fi
  python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()'
}

curl_code() {
  local url="$1"
  local out="${2:-/dev/null}"
  local t="${3:-10}"
  local code
  code="$(curl -sS -o "$out" -w '%{http_code}' --max-time "$t" "$url" 2>/dev/null || true)"
  if [ -z "$code" ]; then
    printf '%s' "000"
  else
    printf '%s' "$code"
  fi
}

echo "=== static module-gap scan ==="
STATIC_JSON="$(static_json)"
printf '%s\n' "$STATIC_JSON" | print_gap_block
STATIC_MISSING="$(printf '%s\n' "$STATIC_JSON" | missing_names)"

if [ -n "$SMOKE_URL" ]; then
  BASE="${SMOKE_URL%/}"
  echo
  echo "=== Mode B — remote $BASE ==="
  health_ok=0
  for _try in 1 2 3; do
    hcode="$(curl_code "$BASE/api/health" /dev/null 15)"
    if [ "$hcode" = "200" ]; then
      health_ok=1
      break
    fi
    echo "health attempt $_try: HTTP $hcode"
    sleep 1
  done
  if [ "$health_ok" != 1 ]; then
    die "/api/health did not return 200 from $BASE"
  fi
  echo "/api/health: 200"

  READY_BODY="$(mktemp)"
  rcode="$(curl_code "$BASE/api/ready" "$READY_BODY" 15)"
  if [ "$rcode" != "200" ] && [ "$rcode" != "503" ]; then
    rm -f "$READY_BODY"
    die "/api/ready returned HTTP $rcode (want 200 or 503)"
  fi
  echo "/api/ready: $rcode"
  if [ "$rcode" = "503" ]; then
    echo "ready checks (503 is a data/volume condition, not a boot failure):"
    python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin).get("checks"), indent=2))' < "$READY_BODY"
  fi
  echo
  echo "=== module gap from /api/ready ==="
  print_gap_block < "$READY_BODY"
  READY_MISSING="$(missing_names < "$READY_BODY")"
  if [ "$STATIC_MISSING" != "$READY_MISSING" ]; then
    echo "WARNING: static scan and /api/ready disagree on lib_modules_missing"
    echo "  static: $STATIC_MISSING"
    echo "  ready:  $READY_MISSING"
  fi
  READY_N="$(missing_count < "$READY_BODY")"
  rm -f "$READY_BODY"
  if [ -n "$STRICT" ] && [ "$STRICT" != "0" ] && [ "$READY_N" != "0" ]; then
    echo "STRICT: lib_modules_missing=$READY_N"
    exit 1
  fi
  echo
  echo "PASS: remote health 200, ready answered ($rcode)"
  exit 0
fi

preflight

IMAGE="campaign-os-smoke:$$"
NAME="campaign-os-smoke-$$"
BUILD_LOG="$(mktemp)"
echo
echo "=== docker build ($IMAGE) ==="
if ! docker build -t "$IMAGE" . >"$BUILD_LOG" 2>&1; then
  echo "docker build failed; last 40 lines:"
  tail -n 40 "$BUILD_LOG"
  rm -f "$BUILD_LOG"
  exit 1
fi
rm -f "$BUILD_LOG"
echo "build ok"

PORT="$(pick_port)"
DATA_TMP="$(mktemp -d)"
echo
echo "=== docker run $NAME  127.0.0.1:${PORT}->8080 ==="
if ! docker run -d --name "$NAME" \
    -p "127.0.0.1:${PORT}:8080" \
    -e PORT=8080 \
    -e DATA_DIR=/data/campaign-os \
    -v "$DATA_TMP:/data/campaign-os" \
    "$IMAGE" >/dev/null; then
  rm -rf "$DATA_TMP"
  die "docker run failed"
fi
trap 'docker rm -f "$NAME" >/dev/null 2>&1; rm -rf "$DATA_TMP"' EXIT

echo "=== poll /api/health (60s) ==="
health_ok=0
for _i in $(seq 1 60); do
  hcode="$(curl_code "http://127.0.0.1:${PORT}/api/health" /dev/null 2)"
  if [ "$hcode" = "200" ]; then
    health_ok=1
    break
  fi
  sleep 1
done
if [ "$health_ok" != 1 ]; then
  echo "health timeout; docker logs:"
  docker logs "$NAME" || true
  exit 1
fi
echo "/api/health: 200"

READY_BODY="$(mktemp)"
rcode="$(curl_code "http://127.0.0.1:${PORT}/api/ready" "$READY_BODY" 10)"
if [ "$rcode" != "200" ] && [ "$rcode" != "503" ]; then
  echo "/api/ready HTTP $rcode; docker logs:"
  docker logs "$NAME" || true
  rm -f "$READY_BODY"
  exit 1
fi
echo "/api/ready: $rcode"
if [ "$rcode" = "503" ]; then
  echo "ready checks (503 is a data/volume condition, not a boot failure):"
  python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin).get("checks"), indent=2))' < "$READY_BODY"
fi

echo
echo "=== module gap from /api/ready ==="
print_gap_block < "$READY_BODY"
READY_MISSING="$(missing_names < "$READY_BODY")"
if [ "$STATIC_MISSING" != "$READY_MISSING" ]; then
  echo "WARNING: static scan and /api/ready disagree on lib_modules_missing — image may differ from the working tree"
  echo "  static: $STATIC_MISSING"
  echo "  ready:  $READY_MISSING"
fi

echo
echo "=== app surface ==="
root_code="$(curl_code "http://127.0.0.1:${PORT}/" /dev/null 10)"
login_code="$(curl_code "http://127.0.0.1:${PORT}/login" /dev/null 10)"
echo "GET /:      $root_code (want 302)"
echo "GET /login: $login_code (want 200)"
if [ "$root_code" != "302" ] || [ "$login_code" != "200" ]; then
  echo "route-registration smoke failed"
  FAIL=1
fi

READY_N="$(missing_count < "$READY_BODY")"
rm -f "$READY_BODY"

if [ -n "$STRICT" ] && [ "$STRICT" != "0" ] && [ "$READY_N" != "0" ]; then
  echo "STRICT: lib_modules_missing=$READY_N"
  exit 1
fi

if [ "$FAIL" != 0 ]; then
  exit 1
fi
echo
echo "PASS: build ok, health 200, ready answered ($rcode)"
exit 0
