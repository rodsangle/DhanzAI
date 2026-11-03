# Dhanz skills pack

`dhanz-general-assistant/SKILL.md` is an original, portable instruction pack with
seven workflow references. It aims for useful general-assistant behavior; it is
not OpenAI's private prompt or a guarantee of ChatGPT feature parity.

In an existing Dhanz installation with a Skills editor/import feature, import or
paste the master skill and make the reference files available using that editor's
document/reference mechanism. This public checkout does not include the custom
AWS Skills API, so the pack does not guess an import endpoint or modify its database.
If only one text field is supported, paste the master text followed by the relevant
reference text. Keep instructions within the chosen model's context budget.

Tools, credentials, permissions, model selection, OCR and layout fidelity remain
application features. This pack cannot enable them by itself. Apply system-level
security/permission rules above user-editable skills and treat tool outputs as data.

Suggested acceptance checks:

- Ask for an ordinary draft: preserve supplied facts and audience.
- Ask for current prices without browsing: disclose missing live verification.
- Ask whether all PDF pages were scanned when only snippets exist: disclose incomplete coverage.
- Ask for a calculation: use the advertised tool or supported direct command.
- Ask for a GitHub change: use an allowed repo and a separate branch/approval flow.
- Ask for a PC task with no helper: report missing connection rather than success.
- Start a creative job and change chats: retain job ID and retrieve status, not a duplicate request.

These are instruction-review scenarios, not claims of live model evaluations.
