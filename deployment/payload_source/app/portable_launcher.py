from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.request
import webbrowser


APP_DIR = Path(__file__).resolve().parent
INSTALL_DIR = APP_DIR.parent
RUNTIME_PYTHON = INSTALL_DIR / "runtime" / "python.exe"
LOG_DIR = INSTALL_DIR / "logs"


def _port_is_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return True
    except OSError:
        return False


def _available_port() -> int:
    for port in range(8501, 8521):
        if not _port_is_open(port):
            return port
    raise RuntimeError("找不到可用的本機連接埠（8501–8520）。")


def _wait_until_ready(url: str, process: subprocess.Popen, timeout: float = 45) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("平台啟動失敗，請查看 logs\\streamlit.log。")
        try:
            with urllib.request.urlopen(url, timeout=1):
                return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("平台啟動逾時，請查看 logs\\streamlit.log。")


def main() -> None:
    LOG_DIR.mkdir(exist_ok=True)
    port = _available_port()
    url = f"http://127.0.0.1:{port}"
    log_path = LOG_DIR / "streamlit.log"
    environment = os.environ.copy()
    environment["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    environment["STREAMLIT_SERVER_HEADLESS"] = "true"

    with log_path.open("a", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                str(RUNTIME_PYTHON),
                "-m",
                "streamlit",
                "run",
                str(APP_DIR / "app.py"),
                "--server.address",
                "127.0.0.1",
                "--server.port",
                str(port),
                "--server.headless",
                "true",
                "--browser.gatherUsageStats",
                "false",
            ],
            cwd=str(APP_DIR),
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        _wait_until_ready(url, process)

    webbrowser.open(url)


if __name__ == "__main__":
    main()
