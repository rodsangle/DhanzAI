"""Two-step verification for DHANZ servers that predate the built-in one (live server add-on).

Authenticator app (TOTP) + single-use recovery codes + "remember this device", at the API paths
the DHANZ app already uses (`/auth/mfa/verify`, `/users/me/mfa/*`, `/users/me/trusted-devices`).

Self-contained: its own tables (`two_step_*`, the `users` table is not changed), its own routes,
and two hooks the deploy script adds (scripts/server/deploy_two_step.py):
  - main.py: `install(app)` before create_app() returns;
  - api/routes/auth.py: in `login`, before session tokens are issued, `login_hook(...)` returns the
    "enter your code" challenge for accounts with two-step verification.
"""


def install(app) -> None:
    from .routes import install as _install

    _install(app)


async def login_hook(db, settings, request, user):
    from .service import login_hook as _hook

    return await _hook(db, settings, request, user)
