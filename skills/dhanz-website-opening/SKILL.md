---
name: dhanz-website-opening
description: Open an explicitly requested website on the user's current browser or Android device.
---

Use the installed `open_website` tool when the user asks to open a website.
For Sortly use its known official address, https://www.sortly.com/.
For unfamiliar services ask for the exact address instead of guessing a domain.

The result prepares a real **Open website** button. Tell the user to tap it;
browser popup restrictions require a user click. Do not claim the website has
already opened, been read, signed into, or modified. No paired PC is needed.

If the user explicitly requests a paired Windows PC, use the existing
`propose_action` open_url workflow and local review instead. Do not infer
permissions to sign in, interact with, or modify a site merely from opening it.
