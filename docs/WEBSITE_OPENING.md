# Website opening on the current device

Web 0.10.3 adds an Open website card to chat. The companion API update registers
`open_website` with prompt guidance and known-site resolution for requests such
as “open Sortly.” Unknown names require the user's exact address, rather than a
fabricated domain. Website addresses must use HTTPS without embedded credentials.

This opens the current browser or Android device after the user presses the
button. It needs no running ROG PC and does not browse, log in or manipulate the
site. Popup restrictions require a user gesture; the tool does not claim to have
opened the site merely by preparing the card. The complete destination is visible
and copyable; launch failures provide a fallback message.

Install `deploy/updaters/install_website_opening.py --apply` on the existing AWS
host. It preserves the current custom API image/settings, adds the tool, checks
startup, then installs the checked web-channel build. Existing Office controls,
clipboard images and server pairing remain. Both steps print rollback details.
Refresh Edge or use `/app/update.html` to refresh the installed Android PWA.

`skills/dhanz-website-opening/SKILL.md` documents the reusable behavior. The
installed tool and prompt guidance make it available without a custom-skills UI.

## Import permission fix

The combined installer keeps its host files private under umask 077. Docker COPY
must explicitly make the copied code readable and its directory traversable (mode
0755 inside the image); otherwise
the image's configured non-root user cannot import them. The corrected installer
uses COPY --chmod=0755 for bootstrap and every added module. Host directories and
files remain private, and the container user remains unchanged. Regression checks
reproduce a failed non-root read with mode 0600 and a successful read after copying
with mode 0755. A failure at the offline startup check leaves the live API untouched.
