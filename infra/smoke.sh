#!/usr/bin/env bash
# Cost-free smoke check against a running dw-companion instance (spec 011).
# Makes no successful /api/chat call: the only POST sends {} and expects 422.
set -euo pipefail
cd "$(dirname "$0")/.."

base_url="${1:-}"

case "$base_url" in
  http://* | https://*) ;;
  *)
    echo "smoke: error: usage: infra/smoke.sh BASE_URL" >&2
    exit 2
    ;;
esac

# Strip exactly one trailing slash.
base_url="${base_url%/}"

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

failed=0
checks_total=7

report_ok() {
  echo "smoke: ok $1"
}

report_fail() {
  echo "smoke: FAIL $1: $2"
  failed=1
}

# Issues one HTTP request, writes the body to $tmp_dir/body and the response
# headers to $tmp_dir/headers, and prints the status code (never raises, even
# on a connection failure, so callers can run under `set -e`).
request() {
  local method="$1" path="$2"
  shift 2
  local status
  status="$(curl -s -o "$tmp_dir/body" -D "$tmp_dir/headers" -w '%{http_code}' \
    -X "$method" "$base_url$path" "$@" 2>/dev/null)" || status="000"
  printf '%s' "$status"
}

# Case-insensitive lookup of one header's value from the last request() call.
header_value() {
  local name="$1"
  grep -i "^$name:" "$tmp_dir/headers" 2>/dev/null \
    | tail -n 1 \
    | sed -E 's/^[^:]*:[[:space:]]*//' \
    | tr -d '\r'
}

check_health() {
  local name="health" attempt status
  for attempt in $(seq 1 30); do
    status="$(request GET /api/health)"
    if [[ "$status" == "200" ]] \
      && grep -Eq '"status"[[:space:]]*:[[:space:]]*"ok"' "$tmp_dir/body"; then
      report_ok "$name"
      return
    fi
    if [[ "$attempt" -lt 30 ]]; then
      sleep 2
    fi
  done
  report_fail "$name" "did not return 200 with status \"ok\" within 30 attempts (last status=$status)"
}

check_home() {
  local name="home" status content_type
  status="$(request GET /)"
  if [[ "$status" != "200" ]]; then
    report_fail "$name" "expected 200, got $status"
    return
  fi
  content_type="$(header_value Content-Type)"
  case "$content_type" in
    text/html*) ;;
    *)
      report_fail "$name" "expected Content-Type text/html, got '$content_type'"
      return
      ;;
  esac
  if ! grep -qF 'href="/assistant/"' "$tmp_dir/body"; then
    report_fail "$name" 'body missing href="/assistant/"'
    return
  fi
  report_ok "$name"
}

check_assistant() {
  local name="assistant" status
  status="$(request GET /assistant/)"
  if [[ "$status" != "200" ]]; then
    report_fail "$name" "expected 200, got $status"
    return
  fi
  if ! grep -qF 'id="chat-form"' "$tmp_dir/body"; then
    report_fail "$name" 'body missing id="chat-form"'
    return
  fi
  report_ok "$name"
}

check_move_page() {
  local name="move-page" status
  status="$(request GET /moves/hack-and-slash/)"
  if [[ "$status" != "200" ]]; then
    report_fail "$name" "expected 200, got $status"
    return
  fi
  report_ok "$name"
}

check_slash_redirect() {
  local name="slash-redirect" status location
  status="$(request GET /moves/hack-and-slash)"
  if [[ "$status" != "307" ]]; then
    report_fail "$name" "expected 307, got $status"
    return
  fi
  location="$(header_value Location)"
  case "$location" in
    */moves/hack-and-slash/) ;;
    *)
      report_fail "$name" "Location '$location' does not end with /moves/hack-and-slash/"
      return
      ;;
  esac
  case "$base_url" in
    https://*)
      case "$location" in
        https://*) ;;
        *)
          report_fail "$name" "Location '$location' does not start with https://"
          return
          ;;
      esac
      ;;
  esac
  report_ok "$name"
}

check_not_found() {
  local name="not-found" status content_type
  status="$(request GET /no-such-page/)"
  if [[ "$status" != "404" ]]; then
    report_fail "$name" "expected 404, got $status"
    return
  fi
  content_type="$(header_value Content-Type)"
  case "$content_type" in
    text/html*) ;;
    *)
      report_fail "$name" "expected Content-Type text/html, got '$content_type'"
      return
      ;;
  esac
  report_ok "$name"
}

check_chat_rejects_invalid() {
  local name="chat-rejects-invalid" status
  status="$(request POST /api/chat -H 'Content-Type: application/json' --data '{}')"
  if [[ "$status" != "422" ]]; then
    report_fail "$name" "expected 422, got $status"
    return
  fi
  if ! grep -qF '"invalid_request"' "$tmp_dir/body"; then
    report_fail "$name" 'body missing "invalid_request"'
    return
  fi
  report_ok "$name"
}

check_health
check_home
check_assistant
check_move_page
check_slash_redirect
check_not_found
check_chat_rejects_invalid

if [[ "$failed" -eq 0 ]]; then
  echo "smoke: all $checks_total checks passed"
  exit 0
fi
exit 1
