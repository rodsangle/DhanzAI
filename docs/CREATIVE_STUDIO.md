# DHANZ Creative Studio (0.7)

The application now has **AI Images**, **AI Videos**, and **My Creations** under the main
chat navigation's **DHANZ Creative Studio** entry. It requires backend account mode;
standalone Ollama chat cannot generate media. Existing assistant functions remain available.

## Implemented workflow

1. Choose an available model and describe the content. Ask Dhanz to help with the prompt if needed.
2. Optionally upload a PNG, JPEG or WebP reference (8 MB, 16 megapixel limit). References also
   appear in the private Knowledge library and can be deleted there.
3. Choose supported aspect ratio, quality, output format, or video duration/resolution.
4. Confirm usage rights and consent. Generate reserves credits and creates a persistent queued job.
5. Leave the screen if desired. Return to My Creations to see its updated status and preview,
   download, share, regenerate a variation, report, cancel, or delete the result. Older history
   is paginated. Progress shows queue/provider stages rather than an invented completion estimate.

Images use the OpenAI Images API contract, including multipart reference edits. The default
model is `gpt-image-2.5-sunburst`; the administrator can configure another compatible model
and HTTPS API endpoint. Supported controls are PNG/JPEG/WebP, low/medium/high quality and
1:1 (1024×1024), 3:2 (1536×1024), or 2:3 (1024×1536) output. Natural-language edits cover
background/object replacement or removal and generative enhancement. Logos, artwork, product
mockups and social graphics are prompt-based uses of this workflow. Enhancement is not a
dedicated deterministic upscaler. Providers can refuse requests or lack model access.

Video uses Runway Gen-4.5 text-to-video and image-to-video tasks: landscape/portrait at
720p, 5 or 10 seconds, MP4. Audio generation, video-input editing and additional video
providers are not exposed. Variations submit a new prompt-based request at the current credit
rate; they do not reuse a deleted reference or promise pixel-identical results.

Provider schemas were checked against the official
[OpenAI image generation reference](https://developers.openai.com/api/reference/resources/images/methods/generate),
[image editing reference](https://developers.openai.com/api/reference/resources/images/methods/edit), and
[Runway API guide](https://docs.dev.runwayml.com/guides/using-the-api/).
The official [OpenAI deprecations page](https://developers.openai.com/api/docs/deprecations)
lists the Sora/Videos API shutdown on September 24, 2026; that unavailable API is not offered.

## Local setup

From the repository root, install Python dependencies (inside your virtual environment):

```powershell
Set-Location backend
python -m pip install -r requirements-dev.txt
python -m alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Before starting, set these in `backend/.env` for a native server, or root `.env` for Docker:

```dotenv
CREATIVE_ENABLED=true
CREATIVE_WORKER_ENABLED=true
OPENAI_API_KEY=your-server-side-key
# Optional independent image/moderation credentials instead of OPENAI_API_KEY:
# CREATIVE_IMAGE_API_KEY=...
# CREATIVE_MODERATION_API_KEY=...
CREATIVE_IMAGE_BASE_URL=https://api.openai.com/v1
CREATIVE_IMAGE_MODEL=gpt-image-2.5-sunburst
CREATIVE_IMAGE_EDITS=true
CREATIVE_IMAGE_TRANSPARENCY=true
RUNWAY_API_KEY=your-server-side-runway-key
CREATIVE_STORAGE=local
CREATIVE_STORAGE_DIR=./data/creations
CREATIVE_MEDIA_DAYS=30
CREATIVE_MAX_MEDIA_MB=100
CREATIVE_MAX_ACTIVE_JOBS=3
CREATIVE_IMAGE_COST=5
CREATIVE_VIDEO_COST_PER_SECOND=10
CREATIVE_MONTHLY_ALLOWANCE=100
```

Image and video providers are unavailable until moderation is configured. Omit `RUNWAY_API_KEY`
to offer images only. The compatible image adapter requires the documented GPT Image parameters
and base64 response shape; for another vendor verify its contract and disable edits or
transparent backgrounds if unsupported. Implement a separate adapter for a different schema.
Never put provider credentials in Flutter defines or application binaries.

The default API process starts a durable queue worker when enabled. To run it separately,
set `CREATIVE_WORKER_ENABLED=false` on the API and run from `backend`:

```powershell
python -m app.generation_jobs
```

Run the Flutter client:

```powershell
Set-Location apps/dhanz_flutter
flutter pub get
flutter run -d windows
# Other targets: flutter run -d chrome; flutter run -d <Android/iOS device id>
```

The existing release workflow builds Windows/Android/iOS; CI also builds the web client.
`media_kit` supplies video playback on Windows, mobile and web. `share_plus` opens the platform's
sharing UI (with a download fallback where the browser cannot share files). Apple/Google
signing and platform build prerequisites still apply. On Windows, if a native Dart build hook
fails because the SDK path contains spaces, use the SDK's existing Windows short path, e.g.
`cmd /c 'for %I in ("C:\path with spaces\flutter") do @echo %~sI'`, then invoke that SDK path.

## Production deployment and storage

Production mode requires `CREATIVE_STORAGE=s3`. Use a private S3/S3-compatible bucket with
public access blocked, encryption enabled and TLS. The server writes objects with AES256
server-side encryption and random keys under `creative/`; it never sets a public ACL.
AWS credentials use the usual boto3 environment/role credential chain. Prefer an instance/task
role scoped to PutObject/GetObject/DeleteObject on this prefix. Configure:

```dotenv
CREATIVE_STORAGE=s3
CREATIVE_S3_BUCKET=your-private-media-bucket
CREATIVE_S3_REGION=us-east-1
# CREATIVE_S3_ENDPOINT=https://your-s3-compatible-service
```

Use the existing production stack, optionally with a separate worker:

```bash
cd deploy
docker compose -f docker-compose.prod.yml -f docker-compose.creative-worker.yml up -d
```

Use a newly built 0.7 backend image (set `DHANZ_IMAGE` accordingly); an older published image
does not contain this implementation. For development Docker, `docker compose up -d --build`
includes the backend changes and persists local creations in the existing data volume.

The database is the durable queue. PostgreSQL row locks serialize account mutations; conditional
leases prevent two workers from submitting the same job. Video task IDs survive process restarts
and can be polled by another worker. Submission intent is committed before calling a provider.
If a process dies between submission and recording the result, the job fails after lease expiry
and releases internal credits rather than blindly submitting a second paid provider request.
The provider may still have charged the operator for an uncertain or canceled request.

Reference and output objects remain private. Authenticated downloads and five-minute HMAC-signed
preview URLs proxy through the backend, with MP4 byte ranges. Preview links are bearer capabilities:
anyone receiving one can use it until expiry; deletion, takedown or account deactivation revokes it.
The application shares a downloaded file only after the user chooses Share. No public gallery is created.
Images retain their original provider bytes and available embedded provenance; application metadata
also records model, provider, generation time and AI disclosure. This is not a new C2PA signature.

Cleanup removes temporary reference copies after terminal jobs, expired media, and deleted media.
Account deletion queues object deletion and remote task cancellation in a durable outbox before
database cascades run. Storage failures are retried. Configure a bucket lifecycle expiration as a
backstop for process crashes between object upload and database commit; choose a duration greater
than `CREATIVE_MEDIA_DAYS`, and account for object versions if bucket versioning is enabled.
Use container memory/CPU limits and monitor provider costs and the worker's logs. Downloads currently
buffer a bounded media file in memory; high-volume deployment should add streaming range retrieval.

## Credits and subscriptions

Internal credits are service units, not provider dollars. Every new request has a user-scoped
idempotency key; reusing it with different inputs returns 409. The server reserves available
credits atomically, consumes them once on success, and releases them once on failure/cancellation.
Repeated cancellations or polling cannot double-refund or double-charge. Current policy fixes
an image's cost per job and video cost per requested second at queue time.

An account receives its allowance once per UTC calendar month when first accessed that month.
Unused credits carry forward. There is no backfill for months the account did not access the service.
The global administrator policy supplies defaults; a per-account allowance supports externally
managed subscription plans. Changes apply at the next month's grant and never change a reserved job.

Administrators can use the Studio administration button to set costs/allowances, review content
reports and remove reported creations. Additional authenticated administrator API endpoints are:

| Endpoint (under `/api/v1/creative`) | Purpose |
|---|---|
| `GET/PUT /admin/policy` | Read/update default costs and allowance |
| `PUT /admin/users/{uuid}/allowance` | Set `monthly_allowance` (null restores default), effective next month |
| `POST /admin/users/{uuid}/credits` | Grant `amount` using a stable `request_key`; duplicate keys grant once |
| `GET /admin/reports` | Review the latest 100 reports |
| `DELETE /admin/jobs/{uuid}` | Revoke access and schedule a takedown |
| `GET /credits/history` | User's latest 100 accounting events |

Payment checkout, credit-pack purchases and payment-provider webhooks are not implemented.
Do not expose administrator grants to clients or treat a client receipt as proof of payment.
An eventual verified payment integration must reuse its stable receipt/event ID for grants.

## Moderation, rights and limitations

OpenAI moderation screens prompts and reference images before generation, then screens image
outputs. Runway's provider moderation applies to generated video. Screening is fail-closed;
errors or refusals release internal credits. Additional rules reject explicit nonconsensual
intimate-content and deceptive-impersonation requests. Usage rights/consent confirmation,
per-account limits, active-job caps, reporting and administrator takedown supplement screening.
These controls cannot establish ownership, consent, identity or every copyright violation.
There is no independent video-frame/audio moderation pipeline. A public launch still needs
abuse operations, terms/privacy review, cost limits and live safety testing.

## Verification

```bash
python -m pytest backend/tests/test_creative.py backend/tests/test_creative_storage.py -q
cd apps/dhanz_flutter
flutter analyze
flutter test
flutter build web --release
```

Provider tests use `httpx.MockTransport`; cloud-storage tests exercise the S3 encryption/privacy
contract with a fake client. Automated tests cover job synchronization, image/video requests,
provider errors, moderation outages, refunds, duplicate requests, concurrent balance exhaustion,
cancellation races, account isolation, reference validation, signed-link expiry, ranges, export,
account deletion, plan allowances and storage cleanup. They do not prove live provider access or
native device playback/sharing. Verify these before distributing a public release:

- Configure real provider keys and a private bucket. Generate and download an image in each format.
- Edit a reference, remove a background to PNG/WebP, and confirm the edit and alpha channel.
- Start a video, leave the screen/restart the app, then return to preview/download its MP4.
- Cancel a running job, inspect its ledger and check the provider's cancellation/billing behavior.
- Test playback, download/share, background return and layout on Windows, Android, iPhone/iPad and web.
- Test bucket permissions, cleanup, account deletion, crash recovery, and PostgreSQL multi-worker contention.

The [original requested upgrade](CREATIVE_REQUIREMENTS.md) is preserved alongside this implementation.
The [workspace verification record](CREATIVE_VERIFICATION.md) lists actual test and build results.
