#!/bin/sh
# Adapter suite: two app instances on the real SDK paths, against the stand-in APIs. Run after `npx next build`.
set -e
cd "$(dirname "$0")/../.."
for p in 3100 3101 4010; do fuser -k $p/tcp 2>/dev/null || true; done
sleep 1
sh tests/e2e/reset-local-db.sh
node tests/mock-api/server.mjs > /tmp/mock.log 2>&1 &
export MODEL_PROVIDER=anthropic ANTHROPIC_API_KEY=sk-ant-test ANTHROPIC_BASE_URL=http://localhost:4010 \
  IMAGE_PROVIDER=openai OPENAI_API_KEY=sk-test OPENAI_BASE_URL=http://localhost:4010/v1 CRON_SECRET=local-test-secret \
  APP_URL=http://localhost:3100 APPS_TEST_BASE=http://localhost:4010 APP_TOKEN_KEY=dGVzdC1vbmx5LWtleS0tbmV2ZXItdXNlLWZvci1yZWE= \
  SLACK_CLIENT_ID=test-slack SLACK_CLIENT_SECRET=test-slack-secret
npx next start -p 3100 > /tmp/a.log 2>&1 &
npx next start -p 3101 > /tmp/b.log 2>&1 &
sleep 6
python3 -I tests/e2e/providers.py
status=$?
for p in 3100 3101 4010; do fuser -k $p/tcp 2>/dev/null || true; done
exit $status
