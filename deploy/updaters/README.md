# Targeted custom-AWS updater scripts

These scripts prepare derivative images of the running `deploy-api-1` container;
they do not execute database migrations or automatically restart production.
Keep your existing Compose files, credentials, custom features and rollback images.

- `prepare_desktop_planner.py`: adds the stateless `/desktop` screenshot planner,
  creates an overlay enabling it, and prints an activation command preserving the
  current Compose file list. Intended for the inspected custom 0010 deployment.
- `prepare_direct_tools.py`: legacy installer bound to the previously inspected
  chat-service checksum. Do not rerun if direct tools already work. It deliberately
  stops if the source differs or an earlier staging directory exists.
- `prepare_github_tools.py`: optional legacy, administrator-only GitHub integration
  bound to the inspected assistant-tools checksum. Existing custom per-account
  GitHub integrations should be retained; do not install a duplicate integration.

Read each script before use. Source-mount, checksum or import failures are blockers,
not reasons to remove its safeguards. Syntax-check with `python3 -m py_compile`
first and run only the component you need. A successful image build is preparation,
not a deployment. Wait for existing in-flight generations before an API recreation;
changing chats is different from restarting the service processing them.

Do not substitute the older public checkout for the custom AWS image. The user
owns its configuration and any activation decision; publishing this source bundle
does not deploy it or transfer secrets.
