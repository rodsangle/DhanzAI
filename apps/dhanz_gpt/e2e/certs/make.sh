#!/bin/sh
# Makes the throwaway certificate the push-notification test (f10) uses for its stand-in on 127.0.0.1.
# Not committed: generated on first run.
set -e
cd "$(dirname "$0")"
[ -f test-push.crt ] && [ -f test-push.key ] && exit 0
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days 3650 \
  -subj "/CN=127.0.0.1" -addext "subjectAltName=IP:127.0.0.1,DNS:localhost" \
  -keyout test-push.key -out test-push.crt 2>/dev/null
echo "made e2e/certs/test-push.{crt,key}"
