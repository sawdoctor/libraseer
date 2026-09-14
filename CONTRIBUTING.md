# Contributing to Libraseer

Libraseer is derived from Stackarr and intentionally keeps several internal
Stackarr names for compatibility. Contributions that fix bugs, improve
reliability, or simplify the code are welcome.

## Dev setup

Clone the existing repository:

    git clone https://github.com/sawdoctor/libraseer.git
    cd stackarr
    cp .env.example .env
    pip install -r requirements.txt
    python run.py

The application listens on port 8484 by default.

The public deployment Compose belongs in the separate Libraseer stack project;
this repository contains the application source.

## Project layout

- `stackarr/recommend.py` — deterministic recommendation engine.
- `stackarr/absclient.py`, `audible.py`, `audnexus.py` — library and metadata sources.
- `stackarr/shelfmark.py` — direct ebook Shelfmark handoff.
- `stackarr/audiobridge.py` — direct Shelfmark-TorBox audiobook handoff; the historical module name is retained for compatibility.
- `stackarr/routes.py` — pages and JSON API.
- `stackarr/templates/` and `stackarr/static/` — UI.

## Guidelines

- Keep recommendations deterministic; there is no AI/model call in the recommendation path.
- Keep configuration environment-driven through `stackarr/config.py`.
- Preserve compatibility names unless a deliberate migration is being made.
- Update version/release documentation when behaviour or configuration changes.
- Test against the relevant real services where practical.

## Releasing

Follow `RELEASING.md`.

The inherited Stackarr Android wrapper and generated GitHub Pages demo are not
part of the Libraseer alpha release.

## Reporting issues

Use the issue templates. Include the Libraseer version shown in the sidebar or
`/api/health`, plus relevant lines from Settings -> Logs or the container logs.
