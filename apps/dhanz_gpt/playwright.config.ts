import { execSync } from "node:child_process";
import { defineConfig } from "@playwright/test";

// Runs against a production build on :3100 with the local Postgres and demo providers (.env.local).
// Specs share one database and run one at a time; global-setup resets it to the demo seed first.
// The push test's throwaway certificate is generated, not committed.
execSync("sh e2e/certs/make.sh", { stdio: "inherit" });

export default defineConfig({
  testDir: "e2e",
  workers: 1,
  fullyParallel: false,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  retries: 0,
  reporter: [["list"], ["json", { outputFile: "test-results/results.json" }]],
  globalSetup: "./e2e/global-setup.ts",
  use: {
    baseURL: "http://localhost:3100",
    viewport: { width: 1440, height: 900 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    // Use an installed Chrome when the Playwright browser download isn't available.
    // A fake microphone (a test tone) for dictation, with the permission prompt auto-accepted per test.
    launchOptions: {
      ...(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {}),
      args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"],
    },
  },
  webServer: [{
    // Stand-ins for Google, Slack and Shopify (and the Claude/OpenAI adapter suite).
    command: "node tests/mock-api/server.mjs",
    url: "http://localhost:4010/__health",
    reuseExistingServer: true,
    timeout: 20_000,
  }, {
    command: "npx next start -p 3100",
    // The stand-in push service in f10 uses a test certificate on 127.0.0.1.
    env: {
      NODE_EXTRA_CA_CERTS: "e2e/certs/test-push.crt",
      PUSH_ALLOWED_HOSTS: "127.0.0.1",
      // App connections against the stand-ins (test-only values).
      APP_URL: "http://localhost:3100",
      APPS_TEST_BASE: "http://localhost:4010",
      APP_TOKEN_KEY: "dGVzdC1vbmx5LWtleS0tbmV2ZXItdXNlLWZvci1yZWE=",
      GOOGLE_CLIENT_ID: "test-google",
      GOOGLE_CLIENT_SECRET: "test-google-secret",
      SLACK_CLIENT_ID: "test-slack",
      SLACK_CLIENT_SECRET: "test-slack-secret",
      SHOPIFY_CLIENT_ID: "test-shop",
      SHOPIFY_CLIENT_SECRET: "shpss_test",
      // Dictation against the stand-in speech endpoint (images stay on the placeholder provider via .env.local).
      OPENAI_BASE_URL: "http://localhost:4010/v1",
      OPENAI_API_KEY: "test-openai",
      IMAGE_PROVIDER: "placeholder",
    },
    url: "http://localhost:3100/login",
    reuseExistingServer: true,
    timeout: 60_000,
  }, {
    // The same build in DHANZ AI account mode, against the stand-in DHANZ API (f18).
    command: "npx next start -p 3101",
    env: {
      AUTH_MODE: "dhanz",
      DHANZ_API_URL: "http://localhost:4010/dhanz/api/v1",
      APP_URL: "http://localhost:3101",
      APP_TOKEN_KEY: "dGVzdC1vbmx5LWtleS0tbmV2ZXItdXNlLWZvci1yZWE=",
      IMAGE_PROVIDER: "placeholder",
    },
    url: "http://localhost:3101/login",
    reuseExistingServer: true,
    timeout: 60_000,
  }],
});
