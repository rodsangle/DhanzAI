# Boss agent for Dhanz

The uploaded Boss starter provides task management, event/reminder records,
rule-based recommendations, simple local messages and assignment tracking.
The Dhanz adaptation exposes those features through the `boss_agent` chat tool.
It uses private per-account SQLite storage rather than the starter's shared
JSON files and interactive CLI. There is no additional public port or daemon.

## Installation

Download the pinned `deploy/updaters/install_boss_agent.py` and run it with
`python3 install_boss_agent.py --apply` in the existing AWS terminal. The helper
builds from the running image, preserves its settings and active Compose files,
verifies the configured private storage is on a writable persistent mount,
checks startup as the image user and waits for API health. It saves a rollback
command and restores the previous image if startup fails. Existing custom
versions of the new modules are refused rather than overwritten. It refuses deployment
while build/media/server jobs are active.

No user tasks, external messages, worker runs or provider requests are started
by installation. Startup registers the tool only; the offline check uses an
empty temporary Boss workspace. The current web/Android PWA can use the new
tool without rebuilding. Start a new chat after installation.

## Use

- “Use Boss to add a task called Review my app requirements, priority 4.”
- “Boss, show my open tasks.”
- “Boss, what task should I do next?”
- “Use Boss to register Research with the role Requirements review.”
- “Boss, assign my Review my app requirements task to Research.”
- “Boss, save this private note: check the app's mobile layout.”

Boss lists saved IDs before updating records instead of inventing them.
Priority 5 is highest. Task recommendations prefer overdue work, then the
earliest deadline, then higher priority. Recommendations are advice; they do
not execute a task. Completing or reassigning a task updates the recorded
agent assignments consistently.

Use ISO-8601 dates with a UTC offset, or supply an IANA timezone such as
`America/New_York`. Naive dates require a timezone. Ambiguous/nonexistent local
times at daylight-saving transitions require clarification. Timestamps are
stored and returned in UTC. Event reminders are checked **on request**;
`event_ack` acknowledges a reminder. This agent does not provide push
notifications or scheduled background delivery.

Agent registration and delegation are **assignment records**, not running AI
workers. Boss does not launch generated agents, execute shell commands,
connect repositories, deploy applications or send email/messages. Real
operations continue to use separately authorized Dhanz integrations. Local
messages are saved as private notes, with an explicit no-delivery result.

## Records and boundaries

Only active signed-in accounts can use the chat tool. Ownership comes from
the authenticated tool context, not a model-supplied user ID. Each account has
`<storage_dir>/boss-agent/<user-uuid>/boss.sqlite3`; directory permissions are
0700 and the database is 0600. Back up this persistent volume alongside the
main database. Records survive API image changes and rollback; the image
rollback command does not erase them. They are separate from the main
PostgreSQL records.

Writes use transactions and server-generated reply/action keys. Retrying the
same action in the same reply reuses the saved result instead of creating a
duplicate. The latest 10,000 action receipts are retained per account. Up to
5,000 task/event/agent/note records are stored per account; lists return at most
50 entries with pagination. Stored titles, roles, tasks and notes are data,
not authorization to perform external actions.

Boss's rules and persistence make no AI/provider calls. Normal conversational
responses still use the configured chat provider and its usual billing.
