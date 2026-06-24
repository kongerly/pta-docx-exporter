from __future__ import annotations

import base64
import json
import os
import subprocess
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app_text import SessionText
from config import AppConfig, resource_root


class SessionError(RuntimeError):
    """Raised when the browser session backend fails."""


@dataclass(slots=True)
class PageSnapshot:
    url: str
    title: str
    html: str
    links: list[dict[str, str]]
    body_text: str = ""
    problem_count: int = 0


class PTASessionManager:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._process: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()

    def ensure_browser_started(self, start_url: str | None = None) -> dict[str, Any]:
        return self._send_command(
            "ensure_browser_started",
            {
                "profileDir": str(self.config.session_profile_dir),
                "startUrl": start_url or self.config.start_url,
                "browserExecutable": str(self._resolve_browser_executable()),
            },
        )

    def login(self, start_url: str) -> dict[str, Any]:
        return self.ensure_browser_started(start_url)

    def wait_for_login(self, timeout_seconds: int = 300) -> dict[str, Any]:
        return self._send_command(
            "wait_for_login",
            {
                "timeoutMs": max(timeout_seconds, 1) * 1000,
            },
        )

    def is_authenticated(self) -> dict[str, Any]:
        return self._send_command("is_authenticated", {})

    def get_current_user(self) -> dict[str, Any]:
        return self._send_command("get_current_user", {})

    def close_login_window(self) -> dict[str, Any]:
        return self._send_command("close_login_window", {})

    def switch_account(self, start_url: str | None = None) -> dict[str, Any]:
        return self._send_command(
            "switch_account",
            {
                "profileDir": str(self.config.session_profile_dir),
                "startUrl": start_url or self.config.start_url,
                "browserExecutable": str(self._resolve_browser_executable()),
            },
        )

    def snapshot(self, url: str, options: dict[str, Any] | None = None) -> PageSnapshot:
        data = self._send_command("snapshot", {"url": url, "options": options or {}})
        return PageSnapshot(
            url=data["finalUrl"],
            title=data["title"],
            html=data["html"],
            links=data["links"],
            body_text=data.get("bodyText", ""),
            problem_count=int(data.get("problemCount") or 0),
        )

    def download_bytes(self, url: str, *, base_url: str = "", referer: str = "") -> tuple[bytes, str]:
        data = self._send_command(
            "download",
            {
                "url": url,
                "baseUrl": base_url,
                "referer": referer,
            },
        )
        return base64.b64decode(data["dataBase64"]), data["contentType"]

    def close(self) -> None:
        process = self._process
        if process is None:
            return
        try:
            self._send_command("shutdown", {}, expect_response=False)
        except Exception:
            pass
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
            self._process = None

    def _ensure_process(self) -> subprocess.Popen[str]:
        if self._process is not None and self._process.poll() is None:
            return self._process

        node_exe = self._resolve_node_executable()
        script_path = resource_root() / "pta" / "browser_service.js"
        if not script_path.exists():
            raise SessionError(SessionText.browser_service_script_missing(str(script_path)))

        env = os.environ.copy()
        node_module_paths = self._resolve_node_module_paths()
        if node_module_paths:
            env["NODE_PATH"] = os.pathsep.join(str(path) for path in node_module_paths)

        self._process = subprocess.Popen(
            [str(node_exe), str(script_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
            env=env,
        )
        return self._process

    def _send_command(
        self,
        command: str,
        payload: dict[str, Any],
        *,
        expect_response: bool = True,
    ) -> dict[str, Any]:
        with self._lock:
            process = self._ensure_process()
            if process.stdin is None or process.stdout is None:
                raise SessionError(SessionText.BROWSER_SERVICE_PIPES_UNAVAILABLE)

            message_id = str(uuid.uuid4())
            envelope = {"id": message_id, "command": command, "payload": payload}
            process.stdin.write(json.dumps(envelope, ensure_ascii=False) + "\n")
            process.stdin.flush()

            if not expect_response:
                return {"ok": True}

            while True:
                line = process.stdout.readline()
                if line:
                    try:
                        response = json.loads(line)
                    except json.JSONDecodeError as error:
                        raise SessionError(SessionText.decode_response_failed(line)) from error
                    if response.get("id") != message_id:
                        continue
                    if not response.get("ok"):
                        raise SessionError(response.get("message", SessionText.UNKNOWN_BROWSER_SERVICE_ERROR))
                    return response

                if process.poll() is not None:
                    stderr = process.stderr.read().strip() if process.stderr is not None else ""
                    self._process = None
                    raise SessionError(stderr or SessionText.BROWSER_SERVICE_EXITED_UNEXPECTEDLY)

    def _resolve_node_executable(self) -> Path:
        candidates = [
            os.environ.get("PTA_NODE_EXE"),
            resource_root() / "runtime" / "node" / "node.exe",
            Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "node" / "bin" / "node.exe",
        ]
        for candidate in candidates:
            if not candidate:
                continue
            path = Path(candidate)
            if path.exists():
                return path
        raise SessionError(SessionText.NODE_RUNTIME_MISSING)

    def _resolve_node_module_paths(self) -> list[Path]:
        candidates = [
            os.environ.get("PTA_NODE_MODULES"),
            resource_root() / "runtime" / "node" / "node_modules",
            Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "node" / "node_modules",
        ]
        resolved: list[Path] = []
        for candidate in candidates:
            if not candidate:
                continue
            path = Path(candidate)
            if path.exists():
                resolved.append(path)
                pnpm_dir = path / ".pnpm"
                if pnpm_dir.exists():
                    for package_dir in pnpm_dir.iterdir():
                        nested_modules = package_dir / "node_modules"
                        if nested_modules.exists():
                            resolved.append(nested_modules)

        unique: list[Path] = []
        seen: set[str] = set()
        for path in resolved:
            key = str(path).lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(path)
        return unique

    def _resolve_browser_executable(self) -> Path:
        candidates = [
            os.environ.get("PTA_BROWSER_EXECUTABLE"),
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
        for candidate in candidates:
            if not candidate:
                continue
            path = Path(candidate)
            if path.exists():
                return path
        raise SessionError(SessionText.BROWSER_MISSING)
