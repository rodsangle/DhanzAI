# App-building model

Dhanz uses the server's existing official OpenAI API connection to generate app
and agent project files. This update connects existing models; it does not train
new model weights or include an OpenAI subscription.

Model discovery reads `/v1/models` and recommends only an ID actually returned
by that API account. Coding families are listed first, with newer numeric model
families before older ones. General GPT text models remain alternatives; audio,
image, chat-only and unrelated model endpoints are excluded. This ranking is a
default, not a benchmark or a guarantee of access, quota or successful output.

New chat-started app/agent builds use the first recommended model unless the
user selects another listed model. The builder and conversational coding
workspace show the recommended choice. Existing jobs and saved projects keep
their original model. Discretion uses the recommendation and still preserves an
explicit model choice. Generation uses the existing Responses API file-submission
protocol; files are validated before a project is marked complete. Usage charges
apply when generation runs. Model discovery does not start generation.

## Installation on the existing AWS deployment

Run `deploy/updaters/install_app_building_model.py --apply` using Python 3 in the
AWS terminal. This is an additive image update from the currently running API.
It preserves existing source, settings and active Compose overlays, checks
startup as the image user, waits for health, and records a rollback command.
Unknown customized defaults are refused. Finish pending build/media/server jobs
first. No migration, key entry, model generation or repository write is performed.

Apply checked web build 0.10.11 or newer with the existing `apply_web_release.py
--apply` helper, then refresh the browser. In **App & agent builder**, choose an
app or Python agent and review **App-building model (OpenAI API)**. Alternatively,
ask in chat: “Create a Python agent that reads CSV files and summarizes totals.
Use the recommended app-building model and provide runnable source and setup.”

API billing/model access still determine whether a job completes. Source
generation does not install, execute, test, deploy or grant capabilities to the
generated agent. Existing authorized workflows remain separate. Local-only
accounts remain blocked from external generation.
