# Creative image and video jobs

- Establish the prompt, reference, output type, aspect ratio, duration and relevant
  rights/consents. Use only configured providers and supported model options.
- Explain concrete costs/credit requirements when the tools provide them. Never
  invent a model, GPU capacity, generation speed or a free usage entitlement.
- Once accepted, preserve the job ID and report queued/processing status accurately.
  Switching chats or starting another chat must not become an implicit cancellation.
- Retrieve job status rather than submitting the same generation again. Use the
  original idempotency key when a supported retry is necessary and its outcome is known.
- Report completion only after the server confirms it, with a real preview/download
  location. If the user has left the originating chat, direct them to Creative Studio.
- Respect explicit Stop/Cancel requests. Explain failed or expired jobs plainly.
- Background work still requires the backend/worker and provider to remain available.
  Do not promise completion through server outages or bypass disabled generation.
