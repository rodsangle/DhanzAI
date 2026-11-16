# Two-step verification (2FA) in DHANZ AI

Status: implemented. Authenticator apps (TOTP) since Phase 5; email codes, "remember this device"
and security alert emails since migration `0010` (web 0.10.16).

**Stack (assumption check).** DHANZ is **FastAPI + SQLAlchemy + PostgreSQL** on the server and
**Flutter** (web, Android, iOS, Windows) for every client. The code below is that code, not a
Node/React sample: a second implementation in a stack DHANZ does not run would be unmaintained
dead code. Every endpoint is plain JSON over HTTPS, so a React client can follow the same flow.

## 1. Recommendation

**Support both, with the authenticator app as the recommended default.**

| | Authenticator app (TOTP) | Email code | SMS (not offered) |
| --- | --- | --- | --- |
| Protects against | password leaks, phishing kits without real-time relay | password leaks | password leaks |
| Weakness | lost phone (use recovery codes) | only as strong as the email account; delivery delays | SIM swap, SS7 interception, number recycling, cost per message, delivery to many countries |
| Works offline | yes | no | no |
| Cost | none | SMTP (already configured) | per message |
| Setup friction | install an app, scan a QR code | none | none |

- **TOTP** is the strongest option DHANZ can offer without hardware keys. A secret on the phone
  never travels again after setup.
- **Email codes** reach people who will not install an authenticator. They still stop the most
  common attack, a reused or leaked password, unless the attacker also controls the mailbox. The
  setup dialog says so ("Only as safe as your email account").
- **No SMS.** It is weaker than both, because phone numbers can be hijacked by SIM swap and SS7
  interception, and it costs money per message. NIST SP 800-63B treats it as "restricted".
- **Next, not now: passkeys (WebAuthn).** They resist phishing outright. Add them as a third
  method later; the `mfa_method` column and the challenge flow are built to take more methods.

One method per account. An email fallback for TOTP accounts would cut their protection down to
email strength, so a lost phone is handled by recovery codes instead.

## 2. Architecture

```
Sign-in: password / Google / Apple (first factor)
        │
        ▼
accounts.finish_sign_in ──► 2FA off ──────────────────────────────► session tokens
        │ 2FA on
        ├─ valid trusted_device_token for this user ─────────────────► session tokens
        │
        ▼
MfaChallenge { mfa_token (JWT, 5–10 min, own jti), method, email_hint, code_sent }
        │   (email method: a 6-digit code bound to this jti is emailed now)
        ▼
POST /auth/mfa/verify { mfa_token, code, remember_device }
        │  accounts.guarded_second_factor → check_second_factor:
        │    totp  → TOTP step newer than mfa_last_step (no replay)
        │    email → code for purpose "mfa:<jti>" (this sign-in only), 5 tries
        │    both  → unused recovery code (Argon2id), consumed
        ▼
session tokens (+ trusted_device_token when remember_device)
```

| Piece | Where |
| --- | --- |
| TOTP maths, secret encryption, recovery code format | `backend/app/core/mfa.py` |
| Challenge token (`MfaTicket`, unique `jti`) | `backend/app/core/security.py` |
| Second-factor checks, email codes, trusted devices, alerts | `backend/app/services/accounts.py` |
| Sign-in endpoints | `backend/app/api/routes/auth.py` |
| Account settings endpoints | `backend/app/api/routes/users.py` |
| Admin reset | `backend/app/api/routes/admin.py` |
| Schema | `backend/app/models/__init__.py`, `backend/alembic/versions/0008_*`, `0010_*` |
| App: challenge screen | `apps/dhanz_flutter/lib/features/auth/auth_screen.dart` (`MfaStepScreen`) |
| App: setup and recovery codes | `apps/dhanz_flutter/lib/features/account/two_factor_dialogs.dart` |
| App: Security settings, remembered devices | `apps/dhanz_flutter/lib/features/account/security_screen.dart` |

Sessions are short-lived access JWTs (15 min) plus rotating refresh tokens. Reuse of a refresh
token revokes its whole family. These are sent as bearer tokens, not cookies, so the API has no
cookie-based CSRF surface; see section 9.

## 3. Database schema

PostgreSQL, as created by migrations `0008` and `0010`:

```sql
-- users (2FA columns)
ALTER TABLE users ADD COLUMN mfa_secret      varchar(255);  -- AES-256-GCM "v1:..." (TOTP only)
ALTER TABLE users ADD COLUMN mfa_enabled_at  timestamptz;   -- NULL = 2FA off
ALTER TABLE users ADD COLUMN mfa_last_step   bigint;        -- last accepted TOTP step (replay guard)
ALTER TABLE users ADD COLUMN mfa_method      varchar(10);   -- 'totp' | 'email'   (0010)

CREATE TABLE mfa_recovery_codes (
  id         uuid PRIMARY KEY,
  user_id    uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  code_hash  varchar(255) NOT NULL,          -- Argon2id of the normalised code
  used_at    timestamptz,                    -- single use
  created_at timestamptz NOT NULL
);
CREATE INDEX ix_mfa_recovery_codes_user_id ON mfa_recovery_codes(user_id);

-- emailed codes: address confirmation, email-2FA sign-in, setup and security changes
CREATE TABLE verification_codes (
  id         uuid PRIMARY KEY,
  user_id    uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  purpose    varchar(20) NOT NULL,           -- 'email' | 'mfa:<jti>' | 'mfa-setup' | 'mfa-manage'
  code_hash  varchar(255) NOT NULL,          -- Argon2id
  attempts   integer NOT NULL DEFAULT 0,     -- 5 wrong tries burn the code
  expires_at timestamptz NOT NULL,
  used_at    timestamptz,
  created_at timestamptz NOT NULL
);

CREATE TABLE trusted_devices (                -- (0010)
  id           uuid PRIMARY KEY,
  user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash   varchar(64) NOT NULL UNIQUE,  -- SHA-256 of a 256-bit random token
  label        varchar(200) NOT NULL,        -- "Chrome on Windows"
  created_at   timestamptz NOT NULL,
  last_used_at timestamptz NOT NULL,
  expires_at   timestamptz NOT NULL
);
CREATE INDEX ix_trusted_devices_user_id ON trusted_devices(user_id);

-- audit_log (existing): every 2FA event is recorded, see section 4.
```

The upgrade sets `mfa_method = 'totp'` on every account that already had 2FA on, so existing users
see no change. The downgrade drops `trusted_devices` and `mfa_method`.

## 4. API

All paths are under `/api/v1`. Errors are `{"detail": "..."}`, written for the person reading them.

**Sign-in**

| Endpoint | Body | Result |
| --- | --- | --- |
| `GET /auth/options` | — | `mfa_email`, `trusted_device_days` (plus the existing sign-in options) |
| `POST /auth/login` | `email, password, trusted_device_token?` | tokens, or `MfaChallenge` |
| `POST /auth/oauth/{google\|apple}` | `id_token, nonce?, trusted_device_token?` | tokens, or `MfaChallenge` |
| `POST /auth/mfa/verify` | `mfa_token, code, remember_device?` | tokens (+ `trusted_device_token`) |
| `POST /auth/mfa/resend` | `mfa_token` | 202; new emailed code, the old one stops working |

`MfaChallenge` = `{mfa_required: true, mfa_token, expires_in, method: "totp"|"email", email_hint, code_sent}`.

**Account settings** (signed in)

| Endpoint | Purpose |
| --- | --- |
| `POST /users/me/mfa/setup` `{password?}` | TOTP: new secret + `otpauth://` URI for the QR code |
| `POST /users/me/mfa/enable` `{code}` | TOTP: confirm, turn on, returns 10 recovery codes |
| `POST /users/me/mfa/email/setup` `{password?}` | Email: emails a setup code (needs a confirmed address) |
| `POST /users/me/mfa/email/enable` `{code}` | Email: confirm, turn on, returns 10 recovery codes |
| `POST /users/me/mfa/email/code` | Email accounts: emails a code for a security change |
| `POST /users/me/mfa/disable` `{code}` | Turn off (second factor or recovery code) |
| `POST /users/me/mfa/recovery-codes` `{code}` | Replace all recovery codes |
| `GET /users/me/mfa/recovery-codes/remaining` | Count of unused codes |
| `GET /users/me/trusted-devices` | Remembered devices |
| `DELETE /users/me/trusted-devices[/{id}]` | Forget one or all |
| `PATCH /admin/users/{id}` `{reset_mfa: true}` | Admin: turn 2FA off for a locked-out user |

**Rules**

| Rule | Value | Where |
| --- | --- | --- |
| TOTP | RFC 6238, SHA-1, 6 digits, 30 s, ±1 step for clock drift | `mfa.py` |
| TOTP replay | a step at or before `mfa_last_step` never matches | `match_step(after=…)` |
| Challenge token lifetime | 5 min (`MFA_CHALLENGE_MINUTES`); email method: max(5, `MFA_EMAIL_CODE_MINUTES`=10) | `create_mfa_token` |
| Email code | 6 digits, 10 min, bound to one challenge `jti`, single use, burnt after 5 wrong tries, new code voids the old | `issue_code` / `consume_code` |
| Wrong second-factor codes | 5 per account per 15 min, then 429 | `guarded_second_factor` |
| Per-IP auth limit | `RATE_LIMIT_AUTH_PER_MINUTE` (10) on login, verify, resend | `_limit` |
| Password lockout | 5 failures per account per 15 min (every email, registered or not) | `login` |
| Resend | 1 per 30 s and 6 per hour per account | `resend_mfa_code`, `mfa_email_code` |
| Setup | TOTP 5/min; email 3/hour; enable 10/min | `users.py` |
| Remember device | 30 days (`TRUSTED_DEVICE_DAYS`, 0 = off), max 20 per account | `remember_device` |
| Recovery codes | 10 × `XXXX-XXXX-XXXX` (~60 bits), Argon2id, single use | `mfa.new_recovery_codes` |

**Audit events** (in `audit_log`, with IP): `auth.mfa_challenge`, `auth.mfa_failed`, `auth.login`
(detail `mfa: totp|email_code|recovery_code|trusted_device`, `remembered`), `user.mfa_enabled`
(method, sessions ended), `user.mfa_disabled`, `user.mfa_recovery_codes_replaced`,
`user.trusted_device_forgotten`, `user.trusted_devices_forgotten`, `admin.user_updated`
(`mfa_reset`).

**Security alert emails** (when SMTP is configured): 2FA turned on, 2FA turned off, a recovery code
was used, new recovery codes created.

## 5. User flows and app screens

**Turn on** (Settings → Security → Two-step verification):
1. When the server offers email codes and the address is confirmed, the user picks
   **Authenticator app (recommended)** or **Code by email**. Otherwise only the authenticator is offered.
2. They confirm with their password (Google/Apple-only accounts skip this).
3. Authenticator: scan the QR code, or copy the key or open the app, then type a code. Email: type
   the code we sent.
4. They see the recovery codes once, can copy them, and press "I saved them".
5. Other devices are signed out, because they signed in with one factor, and an alert email is sent.

**Sign in:** password or Google/Apple, then the "Two-step verification" screen.
- **Authenticator:** "Enter the 6-digit code from your authenticator app."
- **Email:** "We emailed a 6-digit code to a\*\*\*a@example.com", with a **Send a new code**
  button. If the server cannot send email, the screen switches straight to recovery-code entry.
- **Remember this device for 30 days** checkbox, with the note "Only on a device you own".
- **Use a recovery code** link: "Lost your phone?" or "No access to your email?".
- Error states: wrong code ("That code is not correct. Check the time on your phone." or "Use the
  newest code we emailed."), too many tries (429, "Try again in N minutes"), challenge expired
  ("This sign-in has expired. Please start again."), and email unavailable (use a recovery code).

**Remember this device:** the token lives in the platform secure store (Keychain, Keystore, DPAPI,
or browser storage on web). It is kept on sign-out and sent with the next sign-in. Settings →
Security → **Remembered devices** lists each one ("Chrome on Windows · last used … · until …")
with **Forget** and **Forget all devices**.

**Turn off / new recovery codes / delete account:** these need the second factor. Email accounts
get a code sent when the dialog opens, or from the **Send code** button. A recovery code always works.

**Lost access:**
1. A recovery code signs the person in. They then turn 2FA off and on again, or create new codes.
2. No recovery code left: the administrator checks who they are outside the app, then uses
   **Admin → Users → Reset two-step verification**. The reset also forgets their remembered devices.
3. Planned: self-service recovery by email with a **72-hour waiting period**. A request is emailed
   to the owner and can be cancelled from any signed-in device; when the wait ends, 2FA is turned
   off and everyone is alerted. It is not built yet, because a self-service reset is exactly what
   an attacker with the mailbox would use, so the delay and notifications have to be right.

## 6. Code: the important pieces

The repository holds the full code. These are the core rules.

**Accepting a second factor** (`accounts.check_second_factor`):

```python
if user.mfa_method == "email":
    purpose = login_code_purpose(challenge_id) if challenge_id else MANAGE_PURPOSE
    if len(digits) == 6 and await consume_code(db, user, purpose, digits):
        return "email_code"
elif user.mfa_secret is not None:
    step = mfa.match_step(mfa.decrypt_secret(settings, user.mfa_secret), code, after=user.mfa_last_step)
    if step is not None:
        user.mfa_last_step = step          # each 30-second code works once
        return "totp"
# both methods: an unused recovery code (Argon2id, per-code salt), consumed on use
```

**Remembering a device** (`accounts.remember_device` / `trusted_device_ok`):

```python
token = secrets.token_urlsafe(32)                      # 256 bits, shown once
db.add(TrustedDevice(user_id=user.id, token_hash=sha256(token), label=device_label(ua),
                     expires_at=utcnow() + timedelta(days=settings.trusted_device_days)))
# later: valid only for the same user, unexpired; a security change deletes them all
```

**Forgetting devices on security changes** (`auth_service.revoke_user_sessions`): password change,
password reset, "sign out other devices", turning 2FA on, admin deactivation or role change. Turning
2FA off and an admin reset also forget them.

**Challenge screen** (`MfaStepScreen`, Flutter):

```dart
await ref.read(authControllerProvider.notifier)
    .completeMfa(widget.challenge, _code.text, rememberDevice: _remember);
// ApiClient.verifyMfa stores json['trusted_device_token'] in the secure store
```

**QR setup** uses `qr_flutter` on the `otpauth://totp/DHANZ%20AI:<email>?secret=…&issuer=DHANZ%20AI&digits=6&period=30` URI.

## 7. Tests

| Suite | Covers |
| --- | --- |
| `backend/tests/test_accounts.py` | RFC 6238 vectors, replay refused, encrypted secret at rest, TOTP setup/enable/sign-in, recovery codes single-use, per-account wrong-code limit, forged/expired challenge, admin reset, delete account needs the factor, Google/Apple respect 2FA |
| `backend/tests/test_two_step.py` | masked email, device labels, unique challenge ids; email setup needs SMTP + confirmed address + password; code bound to its sign-in; single use; resend voids the old code and is limited; 5 wrong tries burn a code; recovery code alert; managing email 2FA needs a manage code; server flag off keeps existing email accounts working; remembered device skips the step, needs the right password, is per-account, forgotten singly, all, on password change, on admin reset; feature off |
| `apps/dhanz_flutter/test/accounts_test.dart` | TOTP challenge with recovery code, QR setup, legacy servers |
| `apps/dhanz_flutter/test/two_step_test.dart` | email challenge, resend, remember device (token stored, kept on sign-out, sent on next sign-in, step skipped), setup by email, servers without email codes, turning off with an emailed code, forgetting devices |

**Edge cases to watch:** clock drift beyond ±30 s (the code is refused; the message says to check
the time), a code typed with spaces or dashes (normalised), two sign-ins in parallel (each has its
own code), the SMTP server going away after users chose email codes (recovery codes, admin reset),
and Google/Apple sign-in with 2FA (same challenge).

## 8. Rollout

1. **Migration.** Additive only: one nullable column and one new table, so it is safe while old
   code runs. Back up the database first, then `alembic upgrade head`; the backfill marks existing
   2FA users as `totp`.
2. **Feature flags.** `MFA_EMAIL_ENABLED` (default on; off hides email setup and keeps existing email
   accounts working) and `TRUSTED_DEVICE_DAYS` (default 30; 0 hides "remember this device").
3. **Staged.**
   1. Deploy the backend with `MFA_EMAIL_ENABLED=false` and `TRUSTED_DEVICE_DAYS=0`. Nothing
      changes for users.
   2. Publish web 0.10.16. Older apps keep working, because the new fields are optional.
   3. Turn on `TRUSTED_DEVICE_DAYS=30`.
   4. Turn on `MFA_EMAIL_ENABLED=true` once a test account has signed in with email codes.
   5. Later: require 2FA for admin accounts, then encourage it for everyone.
4. **Monitoring** (from `audit_log`):
   - setups by method;
   - share of `auth.mfa_failed` per challenge;
   - recovery-code sign-ins, since a spike means an attack or broken email;
   - resend rate;
   - 429s on the `mfa` buckets;
   - email delivery failures (logged by `send_in_background`);
   - admin resets.
   Alert on any burst of `auth.mfa_failed` from one IP or against one account.
5. **Rollback.** Code first; the migration can stay, because old code ignores the new column and
   table. `alembic downgrade 0009` removes them.

**Live server note.** dhanzai.com runs a customised API image, and its network is not reachable
from the build environment. Before shipping this there, check what the live API has:

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST -H 'content-type: application/json' -d '{}' https://dhanzai.com/api/v1/auth/mfa/verify
curl -s https://dhanzai.com/api/v1/auth/options
```

422 means the TOTP 2FA routes exist; 404 means the live API predates them. The options output
shows whether `mfa_email` is already reported. The live image needs a guarded deploy script, like
the AI-engine and conversation-extras ones: check the live files, build `FROM` the running image,
create the new table, smoke test, then switch with a rollback image. It must not be a blind file
copy, because several of these files are customised on that server.

## 9. Security checklist

- [x] TOTP secrets encrypted at rest (AES-256-GCM, key from `DATA_ENCRYPTION_KEY`, not hashed:
  the server must compute codes). Set `DATA_ENCRYPTION_KEY` separately from `JWT_SECRET`.
- [x] Recovery codes and emailed codes stored only as Argon2id hashes; device tokens and refresh
  tokens as SHA-256 (high entropy).
- [x] Replay: the TOTP step is remembered; email and recovery codes are single use.
- [x] Brute force: per-IP limit, per-account wrong-code limit (5 / 15 min), 5 tries per emailed
  code, password lockout, short challenge lifetime. A 6-digit code is 1 in 10⁶ per try.
- [x] Emailed codes bound to one sign-in challenge, so a code from another sign-in is useless.
- [x] Constant-time comparisons (`hmac.compare_digest`, Argon2 verify).
- [x] 2FA on signs out every other session; any security change forgets remembered devices.
- [x] The challenge token proves only the first factor and cannot be used as a session.
- [x] Alerts on 2FA on/off, recovery-code use and new recovery codes.
- [x] Same response for unknown emails at login (no account enumeration); the email hint is masked.
- [x] Sessions use bearer tokens, not cookies, so there is no ambient-credential CSRF. If a cookie
  session is ever added, it must be `Secure; HttpOnly; SameSite=Lax` (or `Strict`) and every
  state-changing request needs a CSRF token.
- [x] Web: tokens sit in browser storage, so XSS is the real risk. The app never renders HTML from
  model output, and "remember this device" warns "not on shared computers". API responses carry
  `Content-Security-Policy: default-src 'none'` (`backend/app/main.py`).
- [ ] Add a Content-Security-Policy for the web app itself (`/app/` in `deploy/Caddyfile` sends
  none today). Test it against the Flutter web build (CanvasKit, fonts) before enforcing:
  start with `Content-Security-Policy-Report-Only`.
- [ ] Self-service recovery with a waiting period (planned, see section 5).
- [ ] Passkeys/WebAuthn as a phishing-resistant method (planned).
- [ ] Optional policy: require 2FA for admin accounts.

**Common mistakes avoided here:**
- storing TOTP secrets or recovery codes in plain text;
- accepting the same TOTP code twice;
- a long verification window;
- an email code that works for any sign-in;
- unlimited resends;
- "remember me" tokens that survive a password change;
- falling back from TOTP to email (which downgrades it);
- issuing a full session before the second factor;
- telling an attacker whether an account has 2FA before the password is right;
- recovery codes shown more than once;
- no alerts on 2FA changes;
- SMS as the second factor;
- admin resets without auditing.
