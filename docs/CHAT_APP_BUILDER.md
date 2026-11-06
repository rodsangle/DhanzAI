# Build apps from ordinary Dhanz chat

The `build_app` chat tool starts the existing private App & agent builder worker.
It accepts web, Flutter mobile and Python agent requests. It carries the supplied
chat requirements into a persisted project, generates its own request key and
reuses the same build if the tool repeats within a reply. Existing account limits,
rate limits, model discovery, credential checks and local-only policy still apply.
Projects and their status are visible in the existing sidebar workspace. Download
the source ZIP there after generation completes. A status tool reports the actual
job state; generation does not promise a later chat notification.

Flutter projects require `pubspec.yaml`, `lib/main.dart` and `README.md`, rather
than a website's `index.html`. Generated files are checked for the existing file
path, size and credential restrictions. They are not executed, compiled or deployed
by this workflow. The README explains Flutter SDK installation, creation of native
platform scaffolding and building an APK on a suitable development machine.

For vehicle apps, missing manufacturer/hardware integration should produce a
clearly labeled demo adapter while Dhanz asks for make, model, year and compatible
service/hardware. Simulated lock/engine state and vehicle coordinates must never
be reported as real vehicle actions. A phone's GPS is not vehicle tracking.
Credentials belong in a future authenticated integration, not mobile source.

The standalone `install_app_builder_chat.py --apply` updater patches only the
known generation/startup interfaces in the running API image and adds the chat
tool. It preserves other module code and Compose settings, checks startup as the
image's existing user, then recreates only the API. No database migration, browser
rebuild or provider generation is run during installation. The updater saves a
rollback command and restores the previous image if health checks fail.

Generation uses the configured OpenAI API and may incur charges. Model availability
is discovered from that account; it is not evidence that a build has succeeded.
