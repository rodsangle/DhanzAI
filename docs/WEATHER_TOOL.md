# Live weather for the custom AWS API

The saved Weather skill supplies guidance. `get_weather` is the actual tool.
`deploy/updaters/install_weather_tool.py` installs it into a derived image using
only the currently running custom API image. It does not replace that image with
the public backend, modify `.env`, add database migrations, or restart other
services. Original Compose files (including OCR overrides) remain in use.

Run the updater without arguments to prepare and smoke-check the derived image.
Add `--apply` to recreate only the API, then wait for Docker health. It prints a
private rollback-command filename. The updater refuses unfamiliar registry
interfaces or source bind mounts. Its embedded weather module is self-contained;
no package installation is performed on AWS.

## Provider and scope

Weather and city geocoding use Open-Meteo. No API key is required by its free
**non-commercial** endpoint. Review https://open-meteo.com/en/terms and its usage
limits before commercial deployment; commercial use needs a suitable licensed
provider integration. Nothing here purchases a subscription or guarantees free
commercial service.

Only the requested city is geocoded. Optional country and state/region resolve
ambiguity. Coordinates of the resolved city are used for the weather query;
no device GPS is collected or stored. Browser device-location sharing and
website generation/download tools are **not** installed by this updater.

The fixed HTTPS endpoints do not follow redirects. Requests time out, responses
are bounded, input is validated, and failures are returned as tool errors.
Local-only capability mode blocks outbound weather calls. At most two calls per
reply are accepted. There is no background polling or location tracking.

Answers should identify Open-Meteo, its link, modelled data timestamp/timezone,
and units. This does not include severe-weather alerts. Missing alerts must not
be described as no warnings. The server needs outbound HTTPS to
`geocoding-api.open-meteo.com` and `api.open-meteo.com`.

## Verification

Portable mocked tests:

```bash
python -m unittest discover -s tests -p test_weather_update.py -v
```

They cover provider payloads, units, disambiguation, invalid input, redirect
refusal, local-only mode, sanitized failures and the additive installer.
Live provider reachability and the custom API image smoke/health checks must be
verified during installation; mocked tests do not establish those outcomes.

After installation, start a new chat and ask:

> Use get_weather for Miami, Florida, US, in Fahrenheit. Include the source,
> data time and timezone.

Confirm a successful `get_weather` tool activity and actual current data, rather
than a promise to look it up.
