## Dhanz integration notes

Use this workflow as an account-owned saved skill. It grants no new permissions
or tools. The current user request, existing authorization and actual available
capabilities govern actions. Use manage_skill to read the next named Replica
skill when its stage is needed; slash commands in the source mean skill names,
not a special Dhanz command parser.

Check assistant_capabilities and the available tool list before capability claims.
Use build_app for new web/Flutter/Python projects and revise existing owned apps;
include the relevant recon, requirements and design in its instructions. Use
GitHub workspace tools for a connected repository. Preserve the user's chosen
stack: Dhanz's current mobile builder uses Flutter, with a companion browser demo,
not the upstream default Expo. A browser demo is not a compiled native app.
Generated source is not proof of passing tests or deployment.

Planning paths such as replica/recon.md are requested artifacts, not evidence
files have been written. Save them only through an available file/project/GitHub
tool, or present them explicitly as draft text. Small reference templates appear
below. Original reference files and Python helpers are archived with the installed
pack; merely installing a skill does NOT register these scripts as executable
chat tools or expose a filesystem to chat. Do not claim to run their commands.
Use only an actually available authorized named command when applicable; otherwise
explain the missing runner and provide a manual command or an unexecuted test.

A browser Open website button opens a page but does not read or automate it.
Use real live search results when available; request screenshots or page text
when browser inspection is unavailable. Never invent sources, screenshots,
ratings, parity scores, test results or deployment success. Do not assume SSH,
a browser driver, Playwright, payment services or credentials are connected.
Deployment requires the user's actual authorization and applicable connected
workflow; a saved skill never expands server or GitHub grants. Honor existing
explicit authorization rather than repeatedly asking for the same permission.
