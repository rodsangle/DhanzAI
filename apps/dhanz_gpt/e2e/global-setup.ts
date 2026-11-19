import { execSync } from "node:child_process";

// Fresh database with the demo seed before every run.
export default function globalSetup() {
  execSync("sh tests/e2e/reset-local-db.sh", { stdio: "inherit" });
}
