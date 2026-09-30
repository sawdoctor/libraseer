# Libraseer

<p align="center">
  <img src="stackarr/static/icon.svg" alt="Libraseer logo" width="180">
</p>

> **Alpha:** Libraseer `v0.1.0-alpha.7` is for experienced self-hosters. Back
> up its `/config` volume and read the limitations before exposing it to users.

Libraseer is a self-hosted discovery and request interface for a combined eBook
and audiobook library. It learns from what people own, finish, rate, ignore, and
request, then sends approved acquisitions to format-specific Shelfmark services.

Libraseer is derived from [Stackarr](https://github.com/Katalyst88/stackarr)
v1.6.8 by Katalyst. Internal Python package, database, JavaScript, and
`STACKARR_*` names remain during the alpha to preserve compatibility and make
the derivative history reviewable.

## Components

| Role | Project | Purpose |
|---|---|---|
| Discovery and requests | Libraseer | Shared UI, availability, recommendations, approval, and handoff |
| eBook acquisition | [official Shelfmark](https://github.com/calibrain/shelfmark) via [shelfmark-ebooks](https://github.com/sawdoctor/shelfmark-ebooks) | Prowlarr/Usenet search and eBook import |
| Audiobook acquisition | [Shelfmark-TorBox](https://github.com/sawdoctor/shelfmark-torbox) | AudiobookBay/TorBox acquisition and optional Prowlarr/Usenet fallback |

Audiobookshelf, Kavita, Prowlarr, SABnzbd, and TorBox are integrations you run
yourself. Libraseer does not conceal an unpublished bridge or bundled indexer.

## Alpha 7 highlights

- fast typeahead from local/cached catalogue data, with external metadata APIs
  contacted only after a full search is submitted;
- separate, testable eBook Shelfmark and audiobook Shelfmark-TorBox settings;
- an explicit **Try Prowlarr / Usenet** action for a failed audiobook request;
- no automatic Prowlarr fallback, which prevents background indexer/API use;
- portable eBook deployment documentation and focused regression coverage.

## Quick start

Requirements:

- Docker Compose;
- Audiobookshelf (required for sign-in and audiobook library data);
- Shelfmark eBooks when `STACKARR_FORMATS` includes `ebook`;
- Shelfmark-TorBox when `STACKARR_FORMATS` includes `audiobook`;
- Kavita, Calibre-Web, Komga, or OPDS if you want eBook library availability.

```bash
git clone https://github.com/sawdoctor/libraseer.git
cd libraseer
cp .env.example .env
```

Edit `.env`, at minimum setting the Audiobookshelf values, `STACKARR_FORMATS`,
and the matching Shelfmark connection(s). Then validate and start:

```bash
docker compose config
docker compose up -d
```

Open `http://HOST:8484`. The first local account becomes an administrator. You
can then adjust and test integration values in **Settings → Connections**.

The example Compose file stores only Libraseer state under
`LIBRASEER_DATA_DIR` (default `./data`). It does not create or modify the other
services.

## Acquisition configuration

```env
SHELFMARK_EBOOK_URL=http://shelfmark-ebooks:8084
SHELFMARK_EBOOK_USERNAME=libraseer
SHELFMARK_EBOOK_PASSWORD=change-me
SHELFMARK_EBOOK_SOURCE=prowlarr

SHELFMARK_AUDIOBOOK_URL=http://shelfmark-torbox:8084
SHELFMARK_AUDIOBOOK_USERNAME=libraseer
SHELFMARK_AUDIOBOOK_PASSWORD=change-me
SHELFMARK_AUDIOBOOK_SOURCE=audiobookbay
SHELFMARK_AUDIOBOOK_FALLBACK_SOURCE=prowlarr
```

The fallback source is searched only when a user presses **Try Prowlarr /
Usenet** on a failed audiobook request. Typeahead, page loads, and normal
AudiobookBay requests do not invoke it. Libraseer also applies a short per-user
cooldown to repeated fallback clicks.

## Development and validation

```bash
python -m pip install -r requirements.txt
STACKARR_NO_SCHED=true python -m unittest discover -s tests -v
python -m compileall -q stackarr run.py tests
```

See [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) for the deliberately small
public-alpha gate.

## Alpha limitations

- release matching is intentionally conservative and queues one release;
- the Prowlarr audiobook fallback is manual, not automatic;
- a process restart clears the harmless in-memory metadata cache;
- internal `STACKARR_*` names remain for compatibility;
- TorBox symlinks require Shelfmark-TorBox and Audiobookshelf to see their
  target paths at the same absolute container paths.

## Credits and licence

Libraseer retains Stackarr's MIT licence and Katalyst's copyright notice. See
[LICENSE](LICENSE). The eBook deployment uses Shelfmark by CaliBrain, also MIT
licensed. Project maintenance: sawdoctor. Development assistance: OpenAI
ChatGPT/Codex.

Audiobookshelf, Kavita, Prowlarr, SABnzbd, TorBox, Audible, Audnexus, Google
Books, Open Library, and other named integrations remain the work and property
of their respective projects; mention does not imply endorsement.
