# Libraseer 0.1.0-alpha.7

Alpha 7 makes the public installation path clearer and reduces avoidable
external API traffic.

## Added

- local/cached search suggestions that never trigger an external catalogue call;
- a 15-minute catalogue search cache and 24-hour item metadata cache;
- separate eBook Shelfmark and audiobook Shelfmark-TorBox connection settings
  and connection tests;
- a user-triggered **Try Prowlarr / Usenet** action for failed audiobook
  requests, protected by a short cooldown;
- portable Docker Compose, configuration, and release-checklist documentation.

## Changed

- full catalogue searches are cached and book pages can reuse metadata already
  returned by search;
- Libraseer reads both Shelfmark connections from saved settings with environment
  variables as defaults;
- documentation no longer presents the legacy Chaptarr API as the active
  acquisition path.

## Safety

- Prowlarr audiobook fallback is never automatic and uses
  `expand_search=false`;
- only failed audiobook requests can invoke the fallback;
- source/protocol matching remains strict: AudiobookBay uses torrents and the
  Prowlarr fallback uses NZBs;
- no database migration is required.

This remains an alpha for experienced self-hosters. Back up `/config` before
upgrading and complete the clean-install checklist before treating a deployment
as stable.
