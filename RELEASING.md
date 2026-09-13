# Releasing Libraseer

## Release checklist

1. Update `VERSION` and `RELEASE_STAGE` in `stackarr/config.py`.
2. Update `README.md`, `RELEASE_NOTES.md`, `CHANGELOG.md`, `.env.example`, and security documentation where relevant.
3. Confirm the Libraseer validation workflow is green.
4. Create and push the version tag.
5. The tag triggers `.github/workflows/release.yml`, which builds and publishes `ghcr.io/sawdoctor/libraseer` for linux/amd64 and linux/arm64.

The inherited Stackarr generated demo and Android wrapper are intentionally not part of the Libraseer alpha release.

A release is complete when the version and documentation are correct, validation is green, the tag is pushed, and the container image is published successfully.
