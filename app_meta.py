from __future__ import annotations

APP_ID = "PTADocxExporter"
APP_DISPLAY_NAME = "PTA Word 导出工具"
APP_VERSION = "0.3.0"


def build_window_title() -> str:
    return f"{APP_DISPLAY_NAME} v{APP_VERSION}"
