# Libraseer 0.1.0-alpha.8

Alpha 8 fixes audiobook work selection. Previously, requesting `Red Dwarf`
could queue `Red Dwarf: Series V to VIII` because a partial title match earned
enough author/format points. Libraseer now checks the whole work title and
author before ranking formats. If no release matches confidently, it queues
nothing and explains why.

## Fixed

- sequels, collections and TV recordings cannot qualify through a shared title
  prefix when a different book was requested;
- distinctive catalogue subtitles, such as `Infinity Welcomes Careful Drivers`,
  can identify the requested work under an alternate release title;
- separate coauthor names, initials, HTML punctuation and common file/edition
  labels are handled without requiring every coauthor to be listed;
- the verified joint pen name Grant Naylor identifies Rob Grant and Doug Naylor;
- ebook matching recognises distinctive catalogue subtitles paired with
  numbered series labels, accepting the novel's EPUB without accepting its
  sequels, collections, MOBI/HTML files or releases with no known EPUB/PDF format;
- cancelled downloads are identified as cancelled; available download error
  messages are preserved.

## API use and validation

- cached public catalogue metadata is reused. A cache miss for a valid requested
  ASIN may make one Audible product lookup; it does not run another indexer search;
- ebook requests may also resolve their existing Google Books/Open Library
  ID. Returned identity, title and author must agree before a subtitle is used;
- each handoff still makes one Shelfmark release search with
  `expand_search=false`, followed by at most one download submission;
- the regression suite checks Red Dwarf collisions and the actual handoff,
  alongside existing ebook, cache and fallback tests.

## Upgrade and remaining limitations

- update Libraseer only; both Shelfmark services and their configuration can
  remain unchanged. No database migration is required;
- source/protocol rules and the manual-only Prowlarr fallback remain unchanged;
- this fix does not resolve ebook activity API timeouts, ABS listening-history
  authentication, or TorBox/WebDAV
  files that remain invisible after TorBox reports readiness;
- confirm one correct audiobook reaches the library after deployment. A passing
  matcher test is not proof of a completed live download;
- rollback by selecting the previous Libraseer image with the same `/config`.

This remains an alpha for experienced self-hosters. Back up `/config` before
upgrading and complete the clean-install checklist before treating a deployment
as stable.
