# Private SearXNG for the custom AWS server

`deploy/updaters/install_searxng.py --apply` adds a private SearXNG service and
configures the existing custom API to use it. No paid search-provider key is
required. AWS compute, bandwidth and the AI model used to write answers still
have their normal costs. This is not an unlimited or guaranteed search service:
upstream engines can block datacenter traffic, rate-limit requests or be unavailable.

The official image is pinned to the digest checked with this updater. Only seven
web/news engines are enabled. JSON format is enabled because Dhanz's existing
SearXNG adapter needs it. The service is limited to 384 MiB and 0.75 CPU with one
worker, and installation stops if less than 512 MiB of memory is available.
Finish any Flutter builds before running it on the 2-vCPU / 4-GB instance.

No host port or Caddy route is published. Search joins an existing API network;
the API's network list is not replaced, preserving database/Redis connectivity.
An external-network reference in the Compose overlay means an existing Docker
network, not a publicly reachable search service. No firewall rule is needed.

The same current API image is tagged and pinned. All active Compose files remain
in use. Weather/OCR/custom code and `.env` stay unchanged. Only the new search
service and API are started/recreated; database, Redis, Caddy and backups are not
restarted. The server secret is generated locally in a private work directory.
It is not a paid API key or an account credential.

After startup and API health checks, the actual API adapter performs one web
query and one Houston local-news query. Counts are reported separately. A partial
success is labelled; a result count of zero is not verification of that category.
If neither category works, the helper restores the previous API image/provider
and stops SearXNG. It does not bypass CAPTCHAs or engine blocks. A private rollback
command is saved for manual recovery; its path is printed, not secret contents.

Without --apply, only configuration/image preparation occurs. The running API
and other services are unchanged. Unknown source/configuration, ambiguous Docker
networks and unrelated existing overlays are rejected rather than overwritten.

Validation: six portable tests cover isolation/resources, web/news config,
preserving Compose overlays, network selection, startup failure and rollback on
no results. The actual pinned container also started under the proposed limits,
returned HTTP 200 from its local health endpoint and listed the expected seven
web/news engines. Local external search was not performed; usable results and
Daily Local News must be verified on AWS by the updater.

After successful installation refresh dhanzai.com, choose Web: Auto or Web:
Always, then retry Daily Local News for Houston, Texas. A weather-tool lookup is a
separate capability and does not require SearXNG.
