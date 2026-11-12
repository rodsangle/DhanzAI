# Server-hosted models before paid APIs

## Direct tools on the current server

`DIRECT_TOOLS_ENABLED=true` (the default) enables a narrow model-free chat path
for complete commands such as `Calculate 12 * 7`, `What is sqrt(144)?` and
`Convert 100 cm to m`. It reuses the existing validated calculator/converter and
records `server / direct-tools`, zero provider tokens, and tool activity with the
saved message. No model inference is needed, so this is suitable for the 4-GB server.

Ambiguous requests, attached files, forced web research, explicit/preferred models,
project instructions and memory context retain the normal AI path. Invalid math
or unsupported units also retain that path. Reminders and document creation stay
on the existing model/tool flow; they are not guessed by the direct parser.
Set `DIRECT_TOOLS_ENABLED=false` to disable the shortcut. Disabling
`ASSISTANT_TOOLS_ENABLED` also disables it.

These source changes are not in the published `api:latest` image. After applying
them to the AWS checkout, build the API from source while preserving the working
browser configuration:

```bash
cd ~/DhanzAI/deploy
sudo docker compose -f docker-compose.prod.yml -f docker-compose.web.yml -f docker-compose.source.yml build api
sudo docker compose -f docker-compose.prod.yml -f docker-compose.web.yml -f docker-compose.source.yml up -d --no-deps --force-recreate api
```

Test a new chat with `Calculate 12 * 7`: expect `84` and the `direct-tools` label.
Then test ordinary chat to confirm the existing OpenAI configuration still works.
Use all three files for future source builds. To return to the published backend,
recreate `api` using only the production and web files. No database migration is
needed for this change. This source build does not enable Ollama.

DHANZ v0.8.0 already includes Ollama, a `local_first` routing policy, native
assistant tools, and fallback before output starts. This configuration reuses
existing model weights; it does not train new models or promise faster inference.

## Hardware and scope

The existing 2-vCPU, 4-GB Lightsail server also runs PostgreSQL, Redis and the API.
Do not assume it has spare memory for inference. Prefer at least 8 GB RAM for
an initial small-model trial and measure memory and response time before use.
CPU inference may be slower than OpenAI. Keep the current API-only deployment
if latency or memory use is unacceptable. This is an optional experiment, not
a requirement for the working website.

The default `qwen2.5:1.5b` is a small general text model supported by the existing
Ollama adapter. It is a starting candidate, not a benchmarked recommendation.
Do not load multiple specialist models on a small instance. A model's tool-call
support does not guarantee reliable tool selection or reasoning quality.

| Skill | Execution |
|---|---|
| General text, summaries, drafts, simple code | Trial the small Ollama model |
| Calculator, conversions, reminders, Office file generation | Existing backend tools, selected by a tool-capable model |
| Search and document retrieval | Existing search/retrieval services; search credentials may still be needed |
| Image understanding | A configured vision-capable model; the default small model has no vision |
| Image/video generation and speech transcription | Separate configured providers; this profile does not replace them |

## Start without exposing Ollama

Use the existing checkout. From its `deploy` directory, keep all three Compose
files in the commands below so browser hosting remains enabled. Preserve `.env`;
never copy secrets into model prompts or the browser build.

Check `free -h` and `df -h` first. If adequate capacity is available:

```bash
sudo docker compose -f docker-compose.prod.yml -f docker-compose.web.yml -f docker-compose.local-models.yml up -d ollama
sudo docker compose -f docker-compose.prod.yml -f docker-compose.web.yml -f docker-compose.local-models.yml exec ollama ollama pull qwen2.5:1.5b
sudo docker compose -f docker-compose.prod.yml -f docker-compose.web.yml -f docker-compose.local-models.yml exec ollama ollama run qwen2.5:1.5b "Reply with one short sentence introducing yourself."
sudo docker compose -f docker-compose.prod.yml -f docker-compose.web.yml -f docker-compose.local-models.yml up -d --no-deps --force-recreate api
```

The overlay and web Compose file must exist on the deployment server before
running these commands. The model pull requires access to Ollama's registry and
artifact storage. Ollama is reachable only through the Compose network; do not
open port 11434 in Lightsail or add a public Caddy route to it.

## Select and verify

Existing accounts store their own routing policy (normally `balanced`). The
server default does not override saved preferences. In each account's settings,
select **local_first** and choose **Auto** rather than an explicit or preferred
OpenAI model. Explicit and preferred selections take priority over the policy.

Test chat, a calculation, an Office document request, and a simple code request.
Check the model shown on each reply and `docker stats --no-stream`. Measure both
first-response latency and completion time. Validate correctness, not just that
text appeared. Readiness lists configured providers, not a live inference test.

Fallback only occurs for retryable provider failures before text/tool output.
It does not automatically detect weak answers or escalate difficult questions.
Missing models and other non-retryable errors may stop the reply; pull the model
before enabling the API overlay. A slow model can delay fallback. Use an explicit
cloud model for complex work. Images are filtered to vision-capable candidates.

To try another model, pull its exact Ollama tag first, set `DHANZ_LOCAL_MODEL` in
`deploy/.env`, and recreate the API using all three Compose files. Benchmark before
changing the production default. Do not claim all skills are handled locally.

## Roll back

Set each account back to `balanced` or select its working OpenAI model. Then:

```bash
sudo docker compose -f docker-compose.prod.yml -f docker-compose.web.yml up -d --no-deps --force-recreate api
sudo docker compose -f docker-compose.prod.yml -f docker-compose.web.yml -f docker-compose.local-models.yml stop ollama
```

The model volume is retained. No account data or provider credentials are deleted.
This profile has not been deployed or benchmarked on the user's AWS server.
