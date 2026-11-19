Test-only certificate for the stand-in push service in `f10-scheduled.spec.ts` (127.0.0.1).
The test server trusts it through NODE_EXTRA_CA_CERTS (see playwright.config.ts). Never use it anywhere else.
