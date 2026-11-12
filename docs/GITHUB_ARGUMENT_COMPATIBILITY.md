# GitHub reader arguments and write workflow scope

The legacy `github_read` tool accepts `ref`, while `github_workspace` accepts
`branch`. Requests using the other name were rejected locally as "Unsupported
GitHub arguments" before GitHub was called. The compatibility bridge accepts
both names, rejects conflicting values, and delegates to the original reader or
workspace without changing its account ownership, selected repository, or
publication checks.

The old connection reader returned `access: read-only` and "no writes available"
regardless of the token's actual permissions. The bridge reports the reader's
scope separately from token write rights. `token_write_access: not_verified`
is deliberate: successful reads do not verify permission to commit or open PRs.
It points to the existing coding workspace and review/standing-grant workflow.
It does not enable writes on the reader, alter token permissions, create a grant,
merge code, or deploy anything.

`install_github_compat.py --apply` adds the bridge to the current API image,
inserting its startup hook after connected operations are installed. Other
startup hooks and modules are retained. It checks startup as the configured
image user without GitHub or model requests, restarts only the API, saves a
rollback command and restores the old image if readiness fails. Existing
connections, encrypted tokens, saved skills, server pairing, PDF/OCR and browser
assets remain unchanged.

After installation start a new chat and ask github_workspace to read
README.md from the chosen repository and branch, then continue the requested
coding workflow. Report actual access errors instead of inferring permissions
from a reader-only label.
