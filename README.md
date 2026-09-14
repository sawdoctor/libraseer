# Libraseer

> **Alpha:** Libraseer 0.1.0-alpha.2 is intended for experienced self-hosters.
> It works on the maintainer's deployment, but the public installation path is new.

Libraseer is a self-hosted discovery and request interface for one combined
ebook and audiobook library. It learns from the books you own, finish, rate,
ignore, and request, then sends approved acquisitions to format-specific
Shelfmark instances.

Libraseer is derived from [Stackarr](https://github.com/Katalyst88/stackarr)
v1.6.8 by Katalyst. Internal Python package, JavaScript namespace, database
names, and many `STACKARR_*` environment variables retain their Stackarr names
in this alpha for compatibility and reviewability.

## What this alpha adds

- one UI for audiobook and ebook discovery, requests, approvals, and status;
- shared server-wide library availability across users;
- format-aware ownership, taste signals, recommendations, and request history;
- direct ebook handoff to official Shelfmark/Prowlarr/Usenet;
- direct audiobook handoff to Shelfmark-TorBox/AudiobookBay/TorBox;
- no unpublished audiobook bridge dependency.

## Acquisition variables

```env
SHELFMARK_EBOOK_URL=http://shelfmark-ebook:8084
SHELFMARK_EBOOK_USERNAME=
SHELFMARK_EBOOK_PASSWORD=
SHELFMARK_EBOOK_SOURCE=prowlarr

SHELFMARK_AUDIOBOOK_URL=http://shelfmark-torbox:8084
SHELFMARK_AUDIOBOOK_USERNAME=
SHELFMARK_AUDIOBOOK_PASSWORD=
SHELFMARK_AUDIOBOOK_SOURCE=audiobookbay
```

## Validation

```bash
python -m compileall -q stackarr run.py
```

## Alpha limitations

- one audiobook release is queued per request; no automatic audiobook fallback retry;
- audiobook selection is deliberately conservative;
- TorBox symlinks require Shelfmark-TorBox and Audiobookshelf to see the
  relevant host paths at the same absolute container paths;
- internal `STACKARR_*` names remain for compatibility in this alpha.
