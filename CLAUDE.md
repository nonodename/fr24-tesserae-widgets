# CLAUDE.md

A Tesserae widget catalog entry for the FR24 feeder widget (`fr24_node`).
Layout follows the catalog format in [CONTRIBUTING.md](CONTRIBUTING.md):

- `fr24_node/` is the widget: `plugin.json`, `client.js`, `server.py`, `tests/`.
- `widgets.json` is the catalog metadata. Validate against `schema/marketplace.schema.json`.
- `screenshots/fr24_node/{xs,sm,md,lg}.png` are the Browse previews.
- `scripts/refresh_stars.py` updates `stars.json`. Don't hand-edit that file.

## Privacy: this repo is public

Everything committed must be anonymized: no real home coordinates, feeder
IP/hostname, or screenshots showing a real location. Placeholders in use:

- Home: `45.000, -95.000` (test `HOME`, and `plugin.json` defaults).
- Feeder URL: `http://192.0.2.10:8754/flights.json`.

Test aircraft positions must stay at distinct offsets from `HOME`; the
nearest-aircraft test is meaningless if they all sit on it.

## Running the smoke tests

`fr24_node/tests/test_smoke.py` can't run standalone: it imports
`plugins.fr24.server` and needs the `client` fixture from Tesserae's
`conftest.py`. Run it inside a copy of the Tesserae checkout (`../tesserae`),
without touching that repo:

1. rsync `../tesserae` into the scratchpad (exclude `.venv`, `node_modules`, `.git`).
2. Replace its `plugins/fr24` with this repo's `fr24_node/`.
3. From that copy:
   `PYTHONPATH=. ../tesserae/.venv/bin/python -m pytest -p no:cacheprovider -p no:xdist -o addopts="" plugins/fr24/tests/test_smoke.py -q`

The directory id inside Tesserae must be `fr24`, because the render test uses
`/_test/render?plugin=fr24` and `data-plugin="fr24"`. Update those strings if
you test under another id.

## Gotchas

- `plugin.json` `category` must be one of Tesserae's schema values (use
  `transport`). An invalid value makes the loader silently skip the plugin, so
  render tests fail with a missing callsign rather than a schema error.
- `widgets.json` `release.sha256` is still a placeholder, and `tarball_url` /
  `source` point at different repo names. Fix both before publishing a release.
- The author's own Tesserae install has the pre-catalog widget at
  `plugins/fr24` with real settings. Don't copy its values in here.
