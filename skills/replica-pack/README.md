# Replica for Dhanz

Eleven account-owned saved skills adapted from
[Jake Schincariol's Replica pack](https://github.com/Jakeschincariol/replica-skill),
pinned at `77c9436fb3d18c3d58169efb8caf4fe906b0dc51` (MIT).
Original files are preserved under `upstream/`; their checksums are recorded in
`provenance.json`. Copyright and full MIT permission notice are retained both
in the archive and in each generated saved skill.

The skills are replica-recon, replica-architect, replica-design, replica-build,
replica-backend, replica-test, replica-diff, replica-entrepreneur, replica-brand,
replica-launch and replica-deploy. They cover app research, architecture, design,
building, backend integration, testing, comparison, review analysis, branding,
launch materials and deployment planning.

`DHANZ_COMPATIBILITY.md` maps the workflows to Dhanz's actual tools. Small
reference templates are inlined into the records in `skills.json`. Large helper
configuration files and Python helpers remain in the original archive.
The installer does not run them or add executable chat tools, browser automation,
new server permissions or a Claude Code plugin runtime.

Download the published standalone `deploy/updaters/install_replica_skills.py`
and run `python3 ~/install_replica_skills.py --apply` on the existing AWS host.
The installer selects the sole active account, or asks for a sign-in email when
multiple accounts exist. No passwords or API keys are needed. It uses the live
API container's existing database connection without reading or printing its
credentials. There is no image rebuild, restart, migration or AI provider call.

The account-scoped transaction validates all eleven records and the 50-skill
limit before saving. Matching existing records are reused. Conflicting same-named
skills stop the install unless `--replace` is explicitly supplied; a private
backup is written first. Rollback touches only those names for that account and
stops if the skills were edited after installation. Other accounts and skills
are preserved.

Start a new Dhanz chat and say:

> Use replica-recon to research [app name or public URL] and plan my own version.

Slash names in upstream instructions are skill identifiers, not special Dhanz
UI commands. Building through Dhanz's configured AI models may use API credits;
the upstream pack itself is free and requires no separate Replica API key.

Regenerate the reviewed payload with:

```bash
python3 scripts/skills/build_replica_pack.py
python3 scripts/skills/embed_replica_installer.py
```
