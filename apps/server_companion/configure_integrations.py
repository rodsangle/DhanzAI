"""Store OAuth application credentials privately inside the live Dhanz volume."""

import getpass
import json
import subprocess


def main():
    domain = subprocess.run(
        ["/usr/bin/sudo", "/usr/bin/docker", "exec", "deploy-caddy-1", "printenv", "DHANZ_DOMAIN"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not domain or "/" in domain or any(c.isspace() for c in domain):
        raise ValueError("The live public Dhanz domain is unavailable. No settings were changed.")
    origin = "https://" + domain
    print("Dhanz integration domain:", origin)
    print("Register these exact Web application callback addresses with the providers:")
    for name in ("microsoft", "google"):
        print(name + ": " + origin + "/api/v1/integrations/callback/" + name)
    print("Microsoft: https://entra.microsoft.com/ → App registrations → New registration.")
    print("Google: https://console.cloud.google.com/ → Google Auth Platform → Web application client.")
    print("Enter application credentials here only. Do not paste them in ChatGPT.")
    values = []
    for name in ("microsoft", "google"):
        client_id = input(name.title() + " application client ID (blank skips): ").strip()
        if client_id:
            secret = getpass.getpass(name.title() + " client secret VALUE (hidden): ")
            if not secret or any(c.isspace() for c in secret):
                raise ValueError("A client secret was empty or contained whitespace. Nothing was changed.")
            values.append({"provider": name, "client_id": client_id, "client_secret": secret, "origin": origin})
    if not values:
        print("No application settings changed. Configure these when the app registrations are ready.")
        return
    code = """
import json,sys
from app.core.config import get_settings
from app.assistant_studio.integrations import storage
store=storage(get_settings())
for item in json.load(sys.stdin):
    store.configure(item['provider'],item['client_id'],item['client_secret'],item['origin'])
print('Application credentials encrypted and saved. Refresh Settings > Integrations and connect your accounts.')
"""
    result = subprocess.run(  # noqa: S603 - fixed executable/argv; credential values go only through stdin.
        ["/usr/bin/sudo", "/usr/bin/docker", "exec", "-i", "deploy-api-1", "python", "-c", code],
        input=json.dumps(values),
        capture_output=True,
        text=True,
    )
    values.clear()
    if result.returncode:
        raise ValueError("Application configuration failed; raw output was withheld to protect credentials.")
    print(result.stdout.strip())


if __name__ == "__main__":
    try:
        main()
    except (ValueError, subprocess.SubprocessError) as exc:
        raise SystemExit(
            str(exc)
            if isinstance(exc, ValueError)
            else "Could not inspect the live Dhanz server. No credentials were printed."
        ) from None
