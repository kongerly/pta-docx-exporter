# Changelog

## 0.2.0 - 2026-06-24

- Fixed the inline fill-in-the-blank regression where single-line question stems could lose their exported body.
- Added structured export summaries to `ExportResult`.
- Preserved image download/write failures as export warnings instead of silently swallowing them.
- Improved the desktop UI with export confirmation, post-export summary text, and optional output-folder opening.
- Made the build script auto-detect a Node runtime when possible and added a CI-friendly `-SkipRuntimeCopy` switch.
- Added regression and smoke tests plus a minimal Windows CI workflow.
