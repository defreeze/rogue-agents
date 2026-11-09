"""The stage demo: a local dashboard over live runs and recorded traces.

    rogue demo

Standard library only and bound to localhost, so it works offline on a laptop.
Recorded runs always work; live runs need the model endpoint to be reachable.
The page labels every run LIVE or RECORDED.
"""

from __future__ import annotations

import json
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

from .cases import CASES
from .config import Dials, Safeguards
from .corpus import Corpus
from .llm import OpenAICompatLLM
from .runtime import Run
from .trace import Tracer, load


class LiveRun:
    """The single live run the demo can have in flight."""

    def __init__(self):
        self.events: list[dict] = []
        self.done = False
        self.cond = threading.Condition()

    def push(self, event: dict) -> None:
        with self.cond:
            self.events.append(event)
            self.cond.notify_all()

    def finish(self) -> None:
        with self.cond:
            self.done = True
            self.cond.notify_all()


class Demo:
    def __init__(self, root: Path, base_url: str | None, model: str | None):
        self.root = root
        self.llm = OpenAICompatLLM(base_url=base_url, model=model)
        self.live: LiveRun | None = None
        self.lock = threading.Lock()

    def recordings(self) -> list[dict]:
        index = self.root / "recordings" / "index.json"
        return json.loads(index.read_text(encoding="utf-8")) if index.exists() else []

    def recording(self, name: str) -> list[dict] | None:
        known = {r["file"] for r in self.recordings()}
        return load(self.root / "recordings" / name) if name in known else None

    def results(self) -> dict | None:
        path = self.root / "results.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def model_ready(self) -> bool:
        try:
            r = httpx.get(f"{self.llm.base_url}/models", timeout=2.5)
            return r.status_code == 200 and self.llm.model in r.text
        except httpx.HTTPError:
            return False

    def start(self, spec: dict) -> bool:
        with self.lock:
            if self.live and not self.live.done:
                return False
            live = LiveRun()
            self.live = live
        dials = Dials(
            framing=spec.get("framing", "neutral"),
            board=spec.get("board", "shared"),
            read_budget=int(spec.get("read_budget", 4)),
            incentive=spec.get("incentive", "accuracy"),
        )
        guards = Safeguards.parse(",".join(spec.get("safeguards", [])) or "none")
        case = CASES.get(str(spec.get("case", "85")), CASES["85"])
        mode = spec.get("mode", "swarm")
        path = Path("runs") / f"live-{datetime.now():%Y%m%d-%H%M%S}.jsonl"

        def work() -> None:
            tracer = Tracer(path, listeners=[live.push])
            try:
                Run(self.llm, mode=mode, dials=dials, guards=guards, tracer=tracer, case=case).execute()
            finally:
                tracer.close()
                live.finish()

        threading.Thread(target=work, daemon=True).start()
        return True


def make_handler(demo: Demo):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args) -> None:
            pass

        def send_body(self, body: bytes, content_type: str, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def send_json(self, data, status: int = 200) -> None:
            self.send_body(json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json", status)

        def do_GET(self) -> None:
            url = urlparse(self.path)
            query = parse_qs(url.query)
            if url.path == "/":
                html = resources.files("rogue_agents.web").joinpath("index.html").read_bytes()
                self.send_body(html, "text/html; charset=utf-8")
            elif url.path == "/api/status":
                self.send_json({"model": demo.llm.model, "live_ready": demo.model_ready(), "recordings": demo.recordings(),
                                "cases": {k: c.claim for k, c in CASES.items()}})
            elif url.path == "/api/corpus":
                case = CASES.get(query.get("case", ["85"])[0], CASES["85"])
                docs = Corpus.load(case.corpus).docs.values()
                self.send_json({"origin": case.origin_doc, "docs": [
                    {"id": d.id, "title": d.title, "outlet": d.outlet, "date": d.date, "url": d.url, "text": d.text, "role": d.role, "cites": list(d.cites)}
                    for d in docs]})
            elif url.path == "/api/recording":
                events = demo.recording(query.get("name", [""])[0])
                self.send_json(events) if events is not None else self.send_json({"error": "unknown recording"}, 404)
            elif url.path == "/api/results":
                self.send_json(demo.results())
            elif url.path == "/api/stream":
                self.stream()
            else:
                self.send_json({"error": "not found"}, 404)

        def do_POST(self) -> None:
            if urlparse(self.path).path != "/api/run":
                self.send_json({"error": "not found"}, 404)
                return
            spec = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            started = demo.start(spec)
            self.send_json({"started": started}, 200 if started else 409)

        def stream(self) -> None:
            live = demo.live
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            if live is None:
                return
            sent = 0
            try:
                while True:
                    with live.cond:
                        while sent >= len(live.events) and not live.done:
                            live.cond.wait(timeout=15)
                        batch = live.events[sent:]
                        finished = live.done
                    for event in batch:
                        self.wfile.write(f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    sent += len(batch)
                    if finished and sent >= len(live.events):
                        return
            except (BrokenPipeError, ConnectionResetError):
                return

    return Handler


def cmd_demo(args) -> int:
    demo = Demo(Path(args.dir), args.base_url, args.model)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(demo))
    url = f"http://127.0.0.1:{args.port}/"
    ready = demo.model_ready()
    print(f"Rogue Agents demo: {url}")
    print(f"  recordings: {len(demo.recordings())}   model {demo.llm.model}: {'ready' if ready else 'NOT reachable, recorded runs only'}")
    print("  press ? in the page for keys, Ctrl+C here to stop")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def add_demo_parser(sub) -> None:
    p = sub.add_parser("demo", help="open the stage dashboard (live runs and recordings)")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--dir", default="demo", help="folder with recordings/ and results.json")
    p.add_argument("--no-open", action="store_true", help="don't open a browser")
    p.add_argument("--model")
    p.add_argument("--base-url")
    p.set_defaults(fn=cmd_demo)
