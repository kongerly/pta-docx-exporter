# 更新记录

## 0.3.0 - 2026-06-24

- 新增 `app_meta.py` 与 `app_text.py`，统一管理版本号与中文文案。
- 将界面、抓取流程、Word 导出中的用户可见文案集中化，减少散落硬编码。
- 在桌面界面中补充统一版本标识，并优化导出摘要、警告摘要与常见错误提示。
- 将导出文档中的章节标题、样例标题、图片标题与告警前缀统一收口。
- 同步更新 README、CI smoke test 和相关单元测试，保持公开仓库中文体验一致。

## 0.2.0 - 2026-06-24

- Fixed the inline fill-in-the-blank regression where single-line question stems could lose their exported body.
- Added structured export summaries to `ExportResult`.
- Preserved image download/write failures as export warnings instead of silently swallowing them.
- Improved the desktop UI with export confirmation, post-export summary text, and optional output-folder opening.
- Made the build script auto-detect a Node runtime when possible and added a CI-friendly `-SkipRuntimeCopy` switch.
- Added regression and smoke tests plus a minimal Windows CI workflow.
