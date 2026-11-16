"""Cross-platform startup. Credentials are prompted, never saved to disk."""

from __future__ import annotations

import getpass
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import app


ROOT = Path(__file__).resolve().parent


def load_dotenv(path: Path = ROOT / ".env"):
    """Load simple KEY=VALUE pairs without adding a runtime dependency."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def main():
    load_dotenv()
    if not os.environ.get("ORACLE_USER"):
        os.environ["ORACLE_USER"] = input("Usuario/RM Oracle: ").strip()
    if not os.environ.get("ORACLE_PASSWORD"):
        os.environ["ORACLE_PASSWORD"] = getpass.getpass("Senha Oracle: ")
    os.environ.setdefault("ORACLE_DSN", "oracle.fiap.com.br:1521/ORCL")
    app.setup_schema()

    workers = []
    try:
        for node_code, port in app.WORKER_PORTS.items():
            worker_env = os.environ.copy()
            worker_env.pop("ORACLE_USER", None)
            worker_env.pop("ORACLE_PASSWORD", None)
            worker_env.pop("ORACLE_DSN", None)
            worker_env["WORKER_NODE_CODE"] = node_code
            process = subprocess.Popen(
                [sys.executable, str(ROOT / "worker.py"), "--port", str(port)], env=worker_env,
            )
            workers.append(process)
            for _ in range(30):
                if process.poll() is not None:
                    raise RuntimeError(f"Worker {node_code} encerrou antes de ficar pronto.")
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                        health = json.load(response)
                    if health.get("node_code") == node_code:
                        break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError(f"Worker {node_code} nao ficou pronto.")
        print("MVP pronto em http://127.0.0.1:8000", flush=True)
        app.serve()
    finally:
        for process in workers:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    main()
