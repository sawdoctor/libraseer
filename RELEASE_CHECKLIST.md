# Alpha release checklist

Do not add release scope here. Fix only a problem that prevents one of these
checks from passing.

- [ ] Fresh-clone Libraseer, shelfmark-ebooks, and Shelfmark-TorBox.
- [ ] Copy each `.env.example` to `.env` and supply only deployment credentials/paths.
- [ ] Run `docker compose config` for every supplied Compose file.
- [ ] Start all containers and confirm their health/logs are clean.
- [ ] Confirm Libraseer can see both eBook and audiobook library types.
- [ ] Request one small eBook; confirm it reaches official Shelfmark, lands in
      the eBook library, and becomes Available in Libraseer.
- [ ] Request one small audiobook; confirm it reaches Shelfmark-TorBox, completes
      through TorBox/WebDAV, creates a resolving symlink visible to
      Audiobookshelf, and becomes Available in Libraseer.
- [ ] Restart the stack once and confirm state survives.
- [ ] Run `STACKARR_NO_SCHED=true python -m unittest discover -s tests -v`.
- [ ] Run `python -m compileall -q stackarr run.py tests`.
- [ ] Scan the exact commits being tagged for secrets and private paths.
- [ ] Create public images/tags only after every applicable check passes.
