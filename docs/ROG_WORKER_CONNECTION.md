# Connect the tested ROG Wan renderer to Dhanz

This setup follows the successful AMD 8060S WSL preview. It does not turn the
Lightsail CPU into a video GPU. The ROG polls your existing Dhanz HTTPS server,
claims only the paired account's jobs, renders locally, and uploads a validated
MP4. No incoming port, SSH key, video provider API key, or router change is needed.

## What is supported

The Creative Studio model is **ROG Wan 1.3B · 5-second silent preview**:
text to video, 512×288, 16:9, 16 fps, exactly five seconds. This is the same model
snapshot and AMD attention/VAE configuration used for the verified local preview.
It is not Wan 2.2 5B, native HD, a reference-video model, or a long-film renderer.
The previous video model catalog is replaced with this implemented profile;
image generation is unchanged. Longer Moonpack scenes need a separate shot and
assembly workflow. No failed job is automatically retried.

Existing content screening, private media storage, account restrictions, and app
credit rules remain in place. There is no paid video generation API call. This
does not change any existing API use for chat or content screening. The AWS
installer checks the configured screening and private storage before reporting
readiness; an unavailable classifier is never replaced with an allow-all result.

## Install on AWS first

Download `deploy/updaters/install_rog_backend.py` from the reviewed commit and run:

```bash
python3 ~/install_rog_backend.py --apply
```

The installer builds from the **running API image**, patches only the existing
studio startup hook, and adds two modules. It preserves the existing Compose
stack and its storage mounts; it refuses mounted source or nonpersistent upload
storage. Only the API container is recreated, with automatic image rollback if
its health check fails. It refuses to deploy during queued/running builds,
connected operations, or creative generation. The printed rollback command
restores the previous API image. No database migration or browser build is needed.

Both `Content screening: ready` and `Private media storage: ready` are required
before submitting a video. If either is unavailable, share those status lines;
do not queue another render to diagnose it.

## Install and pair on the ROG

In PowerShell, use the same reviewed commit to download
`apps/rog_video_worker/setup_worker.py` into Ubuntu-24.04, source
`~/.local/share/dhanz-rog/amd-env.sh`, then run the downloaded helper with
`python3 ... --apply`. The helper uses the existing `venv-rocm72` and cached model.
It runs the real GPU checks again. There is no package/model download in this step.

Enter your **Dhanz** email and password only at the local pairing prompts. The
password is hidden, the sign-in session is signed out after pairing, and neither
login tokens nor the password are saved. A separate 90-day render-only credential
is saved with mode 0600 in `~/.local/share/dhanz-rog/worker/connection.json`.
The server stores only its hash. The credential cannot read chat history, run
server commands, or claim another user's jobs. Pairing another ROG for the same
account replaces the previous credential, and is refused during an active video.

Keep the foreground terminal and ROG running. Closing it stops the worker. To
restart later in PowerShell:

```powershell
wsl -d Ubuntu-24.04 -- bash -lc 'source ~/.local/share/dhanz-rog/amd-env.sh && ~/.local/share/dhanz-rog/venv-rocm72/bin/python ~/.local/share/dhanz-rog/worker/worker.py'
```

## Test and stop

Refresh Dhanz and select the ROG model in Creative Studio → Video. Set five seconds,
16:9 and 512×288, without a reference attachment. Submit **one** short forest
prompt. Wait for the job to complete and play/download its output. A queued job
is not a completed video. Rendering time depends on the hardware and prompt.

The worker allows one active render per account and owns the shared GPU lock.
It never reclaims an interrupted render automatically. Completed local results
can retry delivery without rerendering; altered results cannot replace an
accepted upload. The server verifies H.264, dimensions, frame count and duration
before exposing output through the existing authenticated media delivery.
Temporary AWS queue results are pruned after seven days while workers poll.
Final app media follows the existing retention policy. ROG output/receipt/log
files remain private locally until you remove them.

Press Ctrl+C to stop. To revoke the connection afterward, run in PowerShell:

```powershell
wsl -d Ubuntu-24.04 -- bash -lc '~/.local/share/dhanz-rog/venv-rocm72/bin/python ~/.local/share/dhanz-rog/worker/worker.py --disconnect'
```

Revocation cancels that account's pending/running ROG jobs and removes the local
credential. It preserves the model cache and completed MP4 files. If a render
process is still running, stop that terminal too.

## Validation limits

Automated checks cover account/token isolation, revocation, atomic claims,
restart behavior without replay, cancellation, upload idempotency, real FFmpeg
MP4 validation, provider limits, runtime integration, and frozen installer source.
Synthetic codec-test clips are not presented as generated video. The AMD GPU and
actual Wan preview were verified on the user's ROG; the new live AWS-to-ROG path
still requires the install, pairing, and one real app job described above.
