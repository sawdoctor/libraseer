# Releasing Libraseer

Every release **must** complete this checklist. Docs and the demo are not
optional polish — they ship with the code, so they are part of the definition of
done for a release.

## Mandatory steps for every release

1. **Bump the version.** Update `VERSION` (and `RELEASE_STAGE` if it changed) in
   `stackarr/config.py`.
2. **Update the docs.** Reflect any new/changed behaviour in:
   - `README.md` (features, config table, quick start)
   - `CHANGELOG.md` (a dated entry for this version)
   - `SECURITY.md` / `.env.example` if anything security- or config-related changed.
3. **Regenerate the demo.** Run `python tools/build_demo.py` and commit the
   refreshed `docs/` output so the GitHub Pages demo matches the release.
   - Verify it: serve `docs/` and confirm pages load with no console errors and
     no broken links (see `tools/build_demo.py` header).
4. **Commit, tag, push.**
   ```bash
   git add -A && git commit -m "vX.Y.Z: <summary>"
   git tag -a vX.Y.Z -m vX.Y.Z
   git push && git push --tags
   ```
   Pushing the tag triggers the **Publish Docker image** workflow
   (`.github/workflows/docker-publish.yml`), which builds and pushes
   `ghcr.io/sawdoctor/libraseer:X.Y.Z` (and `:latest` on the default branch).

## Definition of done

A release is not done until: version bumped · docs updated · `docs/` demo
regenerated and committed · tag pushed · CI image published green.
