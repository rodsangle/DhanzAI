# Microsoft 365, Google and the Integrations page

The 0.10.8 PWA adds **Settings → Integrations**. It preserves the existing GitHub
and Connected AWS operations pages and links to them from the new page.

Each Dhanz account connects its own Microsoft/Google account through the
provider's sign-in page. Files and mail can be authorized separately. Connecting
an account does not start an import, draft, upload, deployment or email send.

## Implemented capabilities

* **OneDrive/Excel:** search/list files, import an XLSX/PDF/other supported file
  into the private Dhanz library, use the existing Excel tools, and export the
  edited document as a new OneDrive copy. OneDrive exports have a unique suffix
  to avoid replacing an existing workbook.
* **Drive/Sheets:** search/list files, import supported Drive files, export native
  Google Sheets to a private XLSX copy, and create a new Google Sheet from an
  owned XLSX document. Google Docs and Slides can also be imported as DOCX/PPTX.
  Spreadsheet edits use the existing local workbook tools; live source sheets
  are not mutated in place.
* **Outlook/Gmail:** list/search recent mail, read bounded text excerpts and save
  an explicitly requested draft in the connected mailbox. There is no sending,
  deletion or attachment-download operation. A mailbox must exist for that service.
* **Settings page:** connect/reconnect/disconnect, select files/mail permissions,
  browse and import cloud files, read recent mail and compose a draft. Use chat
  for exports and native-Sheet creation. The `cloud_integrations` tool reports
  real connection/operation results and attaches imported Dhanz documents.

Example requests after connecting:

> Find Schedule.xlsx in my connected OneDrive and import it.

> Copy Tool ID to LID in my uploaded tracker, then save the edited workbook as a
> new OneDrive copy. Preserve the original workbook.

> Save this edited workbook as a new Google Sheet in my connected Google account.

> Show recent Gmail messages about the schedule and prepare a reply draft for review.

External file/mail text is treated as untrusted data, not authorization to carry
out new instructions. Writes use durable request keys: uncertain writes are not
automatically replayed. Imports retain the existing upload size, scanner and
document-extraction validation. Native Google exports have Google's additional
export-size limit. List responses are bounded; search by filename/subject to
narrow results. Browser and Android PWA sign-in must continue in the same browser
where the connection was started. Native APK OAuth is not included in this build.

## Install the API and checked browser build

Run `deploy/updaters/install_integrations.py --apply` from the reviewed commit.
The wrapper first verifies/stages the checked 0.10.8+49-or-later PWA package, then
builds the integration modules from the **current running API image** and applies
the browser assets. Existing weather, OCR, media, ROG worker, file memory and
spreadsheet hooks are preserved. No PostgreSQL migration or new public port is
needed. The private storage directory must be on an existing persistent mount.
The API and static browser installers print their separate rollback commands.

Installation does **not** configure or connect a provider account. The server
administrator must register one OAuth Web application per provider, once for the
Dhanz deployment. Each user then connects their own account in Settings.

## Microsoft application registration

1. Open [Microsoft Entra](https://entra.microsoft.com/) → App registrations → New
   registration. Use an app name such as “Dhanz AI integrations”. For personal
   OneDrive/Outlook as well as business accounts, select organizational directories
   **and personal Microsoft accounts**.
2. Add a **Web** redirect URI:
   `https://dhanzai.com/api/v1/integrations/callback/microsoft`.
3. Under API permissions, add Microsoft Graph **delegated** permissions
   `User.Read`, `Files.ReadWrite`, `Mail.ReadWrite`, and offline access. The app
   requests OpenID profile/email and offline access during sign-in. It does not
   request Mail.Send or application-wide mailbox permissions. Organizational
   policies may require administrator consent.
4. Create a client secret under Certificates & secrets. Copy its **Value**, not
   its secret ID. Keep the Application (client) ID and secret locally; enter them
   only in the hidden-entry AWS wizard below. Rotate an expiring client secret
   through this same wizard.

## Google application registration

1. Open [Google Cloud Console](https://console.cloud.google.com/) and select/create
   a project. Enable **Google Drive API** and **Gmail API**.
2. Configure Google Auth Platform/consent branding and audience. While the app is
   in Testing, add the actual Google email accounts that will connect as test users.
3. Create an OAuth client of type **Web application**. Add this authorized redirect:
   `https://dhanzai.com/api/v1/integrations/callback/google`.
4. The requested scopes are OpenID profile/email, Drive read-only plus Drive.file,
   and (when mail is selected) Gmail.readonly plus Gmail.compose. Native Sheets
   import/conversion uses Drive API; a Sheets API key is not needed.
5. Copy the client ID/secret into the private AWS wizard. Testing-mode refresh
   tokens can expire after seven days; reconnect when needed. Wider distribution
   of sensitive/restricted scopes may require Google's app verification.

Use your deployment's actual domain if it differs; the AWS wizard prints the
exact callback addresses derived from the live Caddy domain. This is separate
from “Sign in with Google” for logging into Dhanz itself.

## Enter application credentials privately

The API installer writes this host wizard:

```bash
python3 ~/dhanz-integrations-setup/configure_integrations.py
```

It prompts for Microsoft and Google application client IDs and **hidden** secret
values; blank client IDs skip that provider. No provider password, token or app
secret should be pasted into ChatGPT. Values enter the API through stdin, never
command-line arguments. They are encrypted inside the persistent integrations
store. Refresh Settings → Integrations after configuring; no restart is needed.

## Storage and connection lifecycle

OAuth application credentials, tokens, PKCE verifiers and cached write results
are encrypted with a random server-side Fernet key. The persistent
`storage_dir/integrations` folder has mode 0700, and its key/database files have
mode 0600. Back up the **whole private folder**, including `oauth.key`; losing the
key makes saved credentials unreadable. Credential values are never returned by
the account-status API or chat tool.

OAuth uses ten-minute, one-use state, PKCE and a secure HttpOnly browser cookie.
The account is rechecked before completing a connection; a logged-out initiating
session cannot finish it. Disconnect removes local credentials and pending
attempts. A late refresh/sign-in cannot restore a disconnected connection.
Provider-side consent can also be removed in Google/Microsoft account settings;
local Disconnect does not claim to revoke every provider-side grant.
Successful deletion of the Dhanz account also removes its saved integration
credentials and pending attempts without changing other users' connections.

Automated checks use provider mocks, real encryption and the actual HTTP routes.
Live account sign-in and file/mail access still require registered applications,
provider consent and a real account test. No real account is connected by CI.
