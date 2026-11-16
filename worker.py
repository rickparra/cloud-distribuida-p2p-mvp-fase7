"""One local provider process for the phase 7 MVP."""

from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from hosting import HOST_SECONDS, SiteRegistry, html_for_node
from workload import compute_workload


SITES = SiteRegistry()
NODE_ENABLED = True


class WorkerHandler(BaseHTTPRequestHandler):
    node_code = os.environ.get("WORKER_NODE_CODE", "BR-TEE-01")

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/health":
            self._send_json(200, {"status": "READY" if NODE_ENABLED else "DISABLED",
                                  "enabled": NODE_ENABLED, "node_code": self.node_code})
            return
        if path.startswith("/site/"):
            if not NODE_ENABLED:
                self._send_html(503, "<!doctype html><meta charset=\"utf-8\"><h1>Nó desativado</h1><p>Ative o nó no grafo para voltar a servir conteúdo.</p>")
                return
            token = path.removeprefix("/site/")
            status = SITES.status(token)
            if status == "ACTIVE":
                content = SITES.content(token) or html_for_node(self.node_code)
                self._send_html(200, content.replace("__NODE__", self.node_code))
            elif status == "EXPIRED":
                self._send_html(410, "<!doctype html><meta charset=\"utf-8\"><h1>Hospedagem encerrada</h1><p>O prazo de 3 minutos terminou.</p>")
            else:
                self.send_error(404)
            return
        self.send_error(404)

    def do_POST(self):
        if self.path not in ("/execute", "/host", "/stop", "/control"):
            self.send_error(404)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 100_000:
                raise ValueError("Tamanho de tarefa invalido.")
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError("Payload JSON invalido.")
            if self.path == "/control":
                global NODE_ENABLED
                if not isinstance(payload.get("enabled"), bool):
                    raise ValueError("Estado do nó inválido.")
                NODE_ENABLED = payload["enabled"]
                result = {"enabled": NODE_ENABLED, "node_code": self.node_code}
            elif self.path == "/execute":
                if not NODE_ENABLED:
                    raise ValueError("Nó desativado.")
                result = compute_workload(payload, self.node_code)
            elif self.path == "/host":
                if not NODE_ENABLED or payload.get("node") != self.node_code or not isinstance(payload.get("job"), str):
                    raise ValueError("Hospedagem destinada a outro no ou sem tarefa.")
                result = {"status": "ACTIVE", "node_code": self.node_code,
                          "job_code": payload["job"], "token": SITES.start(HOST_SECONDS, payload.get("html") or html_for_node(self.node_code)),
                          "seconds": HOST_SECONDS}
            else:
                if payload.get("node") != self.node_code or not isinstance(payload.get("token"), str):
                    raise ValueError("Site ou no invalido.")
                result = {"stopped": SITES.stop(payload["token"])}
        except (ValueError, json.JSONDecodeError) as exc:
            self._send_json(400, {"error": str(exc)})
            return
        self._send_json(200, result)

    def _send_html(self, status: int, source: str):
        body = source.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print("[worker] " + fmt % args)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), WorkerHandler)
    print(f"Worker {WorkerHandler.node_code}: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
