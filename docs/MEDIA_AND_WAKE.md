# Local media editor and “Hey Dhanz”

The 0.10.6 web client adds **Media editor** and **Voice · Hey Dhanz** to the sidebar.
The installer extends the current API image instead of replacing its custom features.
No models are downloaded, no API key is added, and no media-provider credits are used.

## Media

- Upload an existing video, choose trim start and a 1–60 second duration, then export MP4 (up to 720p at 30 fps).
- Keep, mute, or change the original audio volume; mix a separately uploaded soundtrack.
- Add a narration script in English, Spanish, French, or German. The local eSpeak NG voice is synthetic,
  not a cloned voice or a natural AI narrator. Scripts that exceed the clip length are rejected.
- Download narration alone as WAV (up to 1,500 characters / three minutes).
- Generate a simple chime, beep, or soft tone, alone or mixed into a video.
- Preview completed exports and download them. This does not generate new AI footage or music.

Rendering uses one FFmpeg process at a time, limited threads, 100 MB per input, 60 second video exports,
and bounded subprocess timeouts. Results survive chat navigation. Jobs and original uploaded inputs stay
in the existing persistent storage volume for seven days; users can delete their jobs sooner.
Server restarts mark interrupted renders as failed rather than claiming success or silently replaying them.
Downloads and job lists are account-owned. Request keys deduplicate retries; conflicting retries are rejected.
FFmpeg accepts fixed media demuxers and file/pipe protocols only; user URLs, shell commands and custom filters
are not accepted. A configured ClamAV scanner is honored for uploads. Sources are never overwritten.

The `local_media` chat tool can queue narration/sound jobs and list/check exports. Video file selection,
trimming and mixing use Media editor. Queued jobs are not downloads until their status is complete.

## Wake listening

In **Voice · Hey Dhanz**, explicitly enable **Listen for “Hey Dhanz”** and accept microphone access.
Say “Hey Dhanz, [request]”, or say the wake phrase and then the request within ten seconds.
Only the request is submitted to Dhanz. Recognition pauses while Dhanz answers aloud to avoid feedback.

Browser speech recognition may send microphone audio to the browser vendor's service. It is not guaranteed
on every browser. It is independent of Dhanz's server recording-transcription provider. If unsupported,
use the existing microphone button (which uses the configured transcription provider).
Wake listening is off by default and is not silently restored after navigation or app hiding.
Leaving Voice, hiding the page, locking the device, or turning the switch off releases recognition.
A PWA does not provide a system-wide/locked-phone wake word. Language for the wake recognizer is English.
Existing account policies, model charges for chat replies, and external operation grants still apply.

## Install

Run the published `deploy/updaters/install_media_studio.py --apply` on the AWS host.
It first validates the checked web release and actual live Caddy mount, builds an additive API image with
FFmpeg/eSpeak NG, verifies route schemas and a real offline narration as the image's configured user,
then updates only the API and web client. Existing API secrets, OCR, search, permissions, accounts,
server pairing and other services are preserved. Existing writable persistent media storage is required.
The host needs internet access to its configured APT repositories during image build. CPU usage increases
while exporting; a 2-vCPU Lightsail instance should use short clips.
API and browser rollback commands are printed separately. Private render files remain on the volume.
