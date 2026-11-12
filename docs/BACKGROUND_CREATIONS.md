# Image and video jobs across chats

Creative jobs are durable backend records processed by `generation_jobs.worker_loop`,
not by a widget or a chat SSE subscription. Switching chats, starting a new chat or
leaving Creative Studio must only stop the local view/subscription; cancellation is
an explicit `/creative/jobs/{id}/cancel` request. Keep the configured creative worker
running. Provider failures, credits/limits, explicit cancellation, and server outages
can still affect generation; navigation is not a cancellation signal.

The app-root `creativeActivityProvider` polls account jobs independently of chat and
Studio routes. It shows active generation and a completion/failure notice with an
Open Studio button. Existing active jobs that fall outside the gallery's latest
page are followed by ID. An in-flight response is discarded on account changes.
Temporary network failures preserve tracking and never cancel jobs. Returning to
the foreground refreshes status. Results remain in the server's Creative Studio
gallery even if the app was closed; closed apps cannot display an in-app banner.

This change does not promise to insert results into an originating chat if that
custom deployment does not already support linked creative messages. The gallery
is the durable result location. Closing an unsubmitted generation form before the
server accepts a request is not the same as having an accepted queued job.

Backend tests assert both images and videos finish with downloadable media after
opening another chat and creating a new conversation. Flutter tests cover tracking
across chat changes, off-page active jobs, offline refresh and logout isolation.

Deployment needs the Flutter source changes rebuilt with the repository's pinned
Flutter/Dart versions, then uploaded to the existing public web directory. Preserve
custom frontend changes present in the AWS build; do not overwrite them with an
older checkout. No database migration is needed for the tracker. Actual custom
chat-side generation code should be checked if it sends explicit cancellations on
navigation; the public checkout already detaches chat listeners without stopping
server generation.
