# Keep the state from a weather request

The live provider lookup for Houston, Texas succeeded. Chat can still ask an
unnecessary clarification when its tool arguments omit a state already supplied
by the user. This update binds explicit US city/state text from the current turn
and strengthens the existing tool schema. It does not enable GPS or save location.

`deploy/updaters/install_weather_location.py --apply` derives from the currently
running custom API image, retaining its existing weather module, API keys, OCR,
media/GitHub features and Compose files. It appends a small wrapper to the tool
registry and one current-question context assignment to chat_service. No database
migration or public backend image replacement is performed.

The wrapper understands full US state names and postal abbreviations next to the
requested city. It resolves `Houston Texas`, `Houston, TX`, and `Houston in Texas`
to city Houston / region Texas. It normalizes a combined city argument such as
`Houston, Texas`. Multiple conflicting places or explicitly negated places are
not automatically selected. Other countries remain under the existing lookup's
validation. This bounded parser is not a general geographic understanding engine.

Original weather input validation, privacy checks, request limits and provider
calls remain in force. The state/region becomes a required tool argument (empty
only when the user did not provide one), and its description tells the model not
to ask the user to repeat a state already supplied. Registered tools still need a
model with tool support; this patch does not force every model to call a tool.

The helper refuses unknown interfaces or source mounts. It snapshots the current
image and source, builds offline, smoke-checks imports and the actual tool schema,
then recreates only the API. A rollback command is saved privately. It requires
the original supported weather installation; unrelated weather integrations are
not overwritten. Run without --apply to prepare only.

Seven portable tests check location binding, ambiguity/negation, schema
preservation, original execution/privacy behavior and additive source patches.
The target server runs the image smoke check before deployment. After successful
installation, start a new chat and ask normally for today's Houston, Texas
weather. Confirm a get_weather activity and the provider's location/time/source.
