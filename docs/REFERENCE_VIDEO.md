# Reference-guided short video recreation

In Creative Studio → Video, select a configured model that supports reference images,
then choose **Upload reference image or video**. MP4, MOV, WebM and MKV clips up to
60 seconds are sampled locally. The upload size follows the server's existing upload
limit, capped at 100 MB. Four frames and their timestamps appear in the form.

The opening frame becomes a private Knowledge-library image and is passed through
the existing generation workflow. Type your own motion brief or explicitly choose
**Analyze scenes & motion**. Optional analysis sends four frames to the configured
official OpenAI API, respecting local-only mode. It may use API credits and is not
replayed after an uncertain failure. A retry must be explicitly requested. Successful
analysis is cached. Review and edit the brief before pressing Generate.

Generation uses an opening image plus a text brief. This is a reference-guided
recreation, not full video-to-video motion transfer. Exact actions, cuts, identities,
timing and original audio are not guaranteed or copied. Sparse-frame analysis marks
motion as inferred where appropriate. Existing model durations, resolutions, creative
credits and reference support still apply. A configured generation provider or local
GPU worker is required to produce new footage; sampling alone does not generate it.

The original uploaded video is removed immediately after frame extraction. Sampled
frames are private to the uploading account and expire after seven days. The opening
Knowledge image remains until the user deletes it. Optional analysis checks both
reference ownership and the continuing ownership/existence of that Knowledge image.

Use `install_reference_video.py --apply` on the AWS host. It installs the existing
local-media prerequisite when missing, extends the live API image, then applies the
checked browser package. It preserves the configured image's user, existing services,
server pairing, secrets, OCR, search and permissions. It prints separate rollback
commands for the API stages and browser package. No analysis or generation runs during
installation. The supported hosting target is the current Linux AWS deployment.
