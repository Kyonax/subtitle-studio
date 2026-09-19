"""The local HTTP surface the Vue page drives.

Standard library only, on purpose: the tool stays installable and runnable
offline, and a subtitle workstation should not grow a web framework to show a
preview. The server binds to localhost, refuses requests that did not come from
localhost, and runs exactly one stage at a time (the VRAM law).

Routes (all under /api, everything else serves the built page):

    GET  /api/health                    ffmpeg, GPU, token, resolved paths
    GET  /api/browse?path=              pick an input file
    GET  /api/job?input=&track=         the whole page state
    GET  /api/jobs                      running + recent stages
    GET  /api/events                    server-sent events (log, progress, jobs)
    POST /api/run                       start a stage
    POST /api/segment                   edit one segment's text (Law 1)
    POST /api/speaker                   rename a speaker
    POST /api/track/remove              drop one subtitle track and its files
    GET  /api/styles                    resolved styles.toml + presets
    PUT  /api/styles                    write the whole file
    POST /api/styles/set                set one key, comments preserved
    POST /api/styles/preset             add or remove a [style.NAME] table
    GET  /api/preview                   one PNG frame, the layout truth (Law 4)
    GET  /api/file?path=                serve an artifact (Range-aware)
"""

from __future__ import annotations

import json
import mimetypes
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from subtitle_studio import __version__, paths
from subtitle_studio.config import Settings, load_settings
from subtitle_studio.web.events import EventBus
from subtitle_studio.web.jobs import Busy, BusConsole, JobRunner
from subtitle_studio.web.status import MEDIA_SUFFIXES, job_state, styles_info, track_language

def default_dist_dir() -> Path:
    """Where `npm run build` puts the page: <project>/web/dist. Resolved through
    the same project-root walk the styles resolver uses, so an editable install
    and a source checkout agree."""
    from subtitle_studio.stages.style import project_root

    root = project_root() or Path(__file__).resolve().parents[3]
    return root / "web" / "dist"


PREVIEW_PNG = Path(tempfile.gettempdir()) / "subtitle-studio-web-preview.png"
# The all-languages overlay. Temp, never the work directory — see _combined_subs.
PREVIEW_ASS = Path(tempfile.gettempdir()) / "subtitle-studio-web-preview.ass"
SERVED_SUFFIXES = {".png", ".jpg", ".jpeg", ".ass", ".srt", ".json", ".wav", ".mp3", ".mp4", ".mkv", ".webm", ".mov"}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1", "0.0.0.0"}


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class Studio:
    """Shared state for every request: the event bus, the single job slot, and
    the settings (re-read per request so a config edit lands without a restart)."""

    def __init__(self, default_input: Path | None, dist_dir: Path | None) -> None:
        self.bus = EventBus()
        self.runner = JobRunner(self.bus)
        self.default_input = default_input
        self.dist_dir = dist_dir
        self.preview_lock = threading.Lock()
        self.started_at = time.time()

    @property
    def settings(self) -> Settings:
        return load_settings(None)

    def fonts_dir(self) -> Path | None:
        from subtitle_studio.stages.style import resolve_fonts_dir

        return resolve_fonts_dir(self.settings.paths.fonts_dir)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _input_path(raw: str | None, studio: Studio, required: bool = True) -> Path | None:
    if not raw:
        if studio.default_input:
            return studio.default_input
        if required:
            raise ApiError(400, "no input file selected")
        return None
    path = Path(unquote(raw)).expanduser()
    if required and not path.exists():
        raise ApiError(404, f"{path} not found")
    return path


def _bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "on"}


def _int(value, default=None):
    if value in (None, "", "auto"):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ApiError(400, f"{value!r} is not a whole number") from None


def _gpu_name() -> str | None:
    if not shutil.which("nvidia-smi"):
        return None
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=4, stdin=subprocess.DEVNULL,
        )
        return out.stdout.strip().splitlines()[0] if out.returncode == 0 and out.stdout.strip() else None
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# stage dispatch
# --------------------------------------------------------------------------- #

def _ensure_track(
    input_media: Path,
    workdir: Path,
    settings: Settings,
    track: str,
    preset: str | None,
    position: str | None,
    fonts_dir: Path | None,
    styles_path: Path | None,
    progress,
    span: tuple[float, float] = (0.0, 1.0),
):
    """Bring ONE subtitle track up to date: translate it when its text is
    missing or stale (Law 3), then build its .ass. Returns the .ass path.

    `span` scales this track's progress into its slice of a batch, so a run
    over five languages still moves one honest bar.
    """
    from subtitle_studio.stages.style import run_style
    from subtitle_studio.stages.translate import run_translate
    from subtitle_studio.web.status import translate_state

    low, high = span

    def scaled(message: str, fraction: float) -> None:
        if progress:
            progress(message, low + (high - low) * max(0.0, min(fraction, 1.0)))

    label = track or "source"
    if track:
        state = translate_state(workdir, settings, track)
        if state != "fresh":
            scaled(f"{label}: translating ({state})", 0.05)
            run_translate(
                input_media, workdir, settings,
                None if track == "swap" else track, swap=(track == "swap"),
                on_progress=lambda msg, frac: scaled(f"{label}: {msg}", 0.05 + 0.75 * frac),
            )
    scaled(f"{label}: building subtitles", 0.85)
    return run_style(
        input_media, workdir, lang=track or None, styles_path=styles_path,
        fonts_dir=fonts_dir, preset=preset, position=position,
        on_progress=lambda msg, frac: scaled(f"{label}: {msg}", 0.85 + 0.15 * frac),
    )


def _requested_tracks(options: dict, workdir: Path) -> list[str]:
    """The tracks a batch should touch: what the page asked for, or everything
    this work directory already carries."""
    asked = options.get("tracks")
    if isinstance(asked, list) and asked:
        return [str(item or "") for item in asked]
    from subtitle_studio.web.status import subtitle_tracks

    return [track["id"] for track in subtitle_tracks(workdir, load_settings(None), None)]


def _stage_job(studio: Studio, body: dict) -> tuple[str, str, object]:
    """(stage, label, fn) for a /api/run request — the same stage functions the
    CLI calls, wrapped so their progress callback reaches the page."""
    stage = (body.get("stage") or "").strip()
    options = body.get("options") or {}
    settings = studio.settings
    track = (options.get("track") or "").strip() or None
    fonts_dir = studio.fonts_dir()

    if stage == "models":
        component = options.get("component") or "all"

        def pull_models(progress):
            from rich.console import Console

            from subtitle_studio.models_pull import pull

            pull(component, settings, Console(file=BusConsole(studio.runner), force_terminal=False, width=100))
            return f"models: {component}"

        return stage, f"pull models ({component})", pull_models

    input_media = _input_path(body.get("input"), studio)
    workdir = paths.studio_dir(input_media, None)
    styles_path = Path(options["styles"]).expanduser() if options.get("styles") else None
    preset = (options.get("preset") or "").strip() or None
    position = (options.get("position") or "").strip() or None

    if stage == "extract":
        from subtitle_studio.stages.extract import run_extract

        return stage, "extract audio", lambda progress: run_extract(input_media, workdir, progress)

    if stage == "transcribe":
        from subtitle_studio.stages.transcribe import run_transcribe

        language = (options.get("language") or "").strip() or None
        if language == "auto":
            language = None
        if options.get("model"):
            settings.asr.model = options["model"]
        batch = _int(options.get("batch"))
        return stage, "transcribe", lambda progress: run_transcribe(
            input_media, workdir, settings, language=language, batch_size=batch, on_progress=progress
        )

    if stage == "relisten":
        from subtitle_studio.stages.transcribe import relisten_segment

        seg_id = _int(options.get("segment"))
        if seg_id is None:
            raise ApiError(400, "relisten needs a segment id")
        return stage, f"relisten segment {seg_id}", lambda progress: relisten_segment(
            input_media, workdir, settings, seg_id, on_progress=progress
        )

    if stage == "diarize":
        from subtitle_studio.stages.diarize import run_diarize

        return stage, "identify speakers", lambda progress: run_diarize(
            input_media, workdir, settings,
            min_speakers=_int(options.get("min_speakers")),
            max_speakers=_int(options.get("max_speakers")),
            on_progress=progress,
        )

    if stage == "languages":
        def annotate(progress):
            from subtitle_studio.langid import annotate_segments
            from subtitle_studio.schema import load_transcript, save_transcript

            transcript_file = paths.transcript_path(workdir)
            transcript = load_transcript(transcript_file)
            progress("detecting the language of every segment", 0.3)
            annotate_segments(transcript)
            save_transcript(transcript, transcript_file)
            return transcript_file

        return stage, "detect languages", annotate

    if stage == "translate":
        from subtitle_studio.stages.translate import run_translate

        swap = _bool(options.get("swap"))
        to_lang = (options.get("to") or "").strip() or None
        if swap:
            to_lang = None
        elif not to_lang:
            raise ApiError(400, "pick a target language, or turn on swap")
        label = "translate (swap)" if swap else f"translate to {to_lang}"
        return stage, label, lambda progress: run_translate(
            input_media, workdir, settings, to_lang,
            translate_all=_bool(options.get("all")), swap=swap, on_progress=progress,
        )

    if stage == "style":
        from subtitle_studio.stages.style import run_style

        return stage, "build subtitles", lambda progress: run_style(
            input_media, workdir, lang=track, styles_path=styles_path, fonts_dir=fonts_dir,
            preset=preset, position=position, on_progress=progress,
        )

    if stage == "render":
        from subtitle_studio.stages.render import run_render
        from subtitle_studio.stages.style import run_style_combined

        if options.get("codec"):
            settings.render.codec = options["codec"]
        # NOT "preset": that key already names the [style.NAME] table, and
        # feeding an encoder preset into it fails as an unknown style preset.
        if options.get("encoder_preset"):
            settings.render.preset = options["encoder_preset"]
        if options.get("cq") not in (None, ""):
            settings.render.cq = _int(options.get("cq"), settings.render.cq)

        # Every language painted in at once, from the same document the preview
        # showed. One video, all subtitles — not switchable streams.
        if _bool(options.get("all")):
            def burn_all(progress):
                combined = run_style_combined(
                    input_media, workdir, styles_path=styles_path, fonts_dir=fonts_dir,
                    preset=preset, position=position,
                    on_progress=lambda msg, frac: progress(msg, frac * 0.05),
                )
                if combined is None:
                    raise ApiError(400, "only one subtitle here — burn it as a single language")
                return run_render(
                    input_media, workdir, settings, "all", fonts_dir=fonts_dir,
                    on_progress=lambda msg, frac: progress(msg, 0.05 + frac * 0.95),
                    subs=combined,
                )

            return stage, "burn every language", burn_all

        target = track_language(workdir, track)
        return stage, "burn video", lambda progress: run_render(
            input_media, workdir, settings, target, fonts_dir=fonts_dir, on_progress=progress
        )

    if stage == "add_track":
        swap = _bool(options.get("swap"))
        to_lang = (options.get("to") or "").strip().lower()
        if swap:
            to_lang = "swap"
        if not to_lang:
            raise ApiError(400, "which language? pass a code like en, pt, fr — or swap")
        if paths.transcript_path(workdir, to_lang).exists():
            raise ApiError(400, f"this video already carries a {to_lang} subtitle")
        label = "add bilingual cross" if swap else f"add {to_lang} subtitles"
        return stage, label, lambda progress: _ensure_track(
            input_media, workdir, settings, to_lang, preset, position, fonts_dir, styles_path, progress
        )

    if stage == "build_tracks":
        wanted = _requested_tracks(options, workdir)
        if not wanted:
            raise ApiError(400, "no subtitle tracks to build yet")

        def build_all(progress):
            made = []
            for index, item in enumerate(wanted):
                span = (index / len(wanted), (index + 1) / len(wanted))
                made.append(str(_ensure_track(
                    input_media, workdir, settings, item, preset, position,
                    fonts_dir, styles_path, progress, span,
                )))
            return ", ".join(Path(path).name for path in made)

        return stage, f"build {len(wanted)} subtitle track(s)", build_all

    if stage == "mux":
        wanted = _requested_tracks(options, workdir)
        if not wanted:
            raise ApiError(400, "build at least one subtitle track first")

        def deliver(progress):
            from subtitle_studio.stages.mux import run_mux

            languages = []
            for index, item in enumerate(wanted):
                span = (index / (len(wanted) + 1), (index + 1) / (len(wanted) + 1))
                _ensure_track(
                    input_media, workdir, settings, item, preset, position,
                    fonts_dir, styles_path, progress, span,
                )
                languages.append(track_language(workdir, item or None))
            return run_mux(
                input_media, workdir, tracks=languages,
                on_progress=lambda msg, frac: progress(msg, len(wanted) / (len(wanted) + 1) + frac / (len(wanted) + 1)),
            )

        return stage, "generate the video with all subtitles", deliver

    if stage == "run":
        from subtitle_studio.pipeline import RunPlan, force_from, run_pipeline

        if options.get("force"):
            force_from(workdir, options["force"])
        # "run everything" means everything for the subtitle the page is on, so
        # the selected track decides the language unless one is passed outright.
        swap = _bool(options.get("swap")) or track == "swap"
        to_lang = (options.get("to") or "").strip() or (track if track and track != "swap" else None)
        plan = RunPlan(
            input_media=input_media, workdir=workdir, settings=settings,
            to_lang=None if swap else to_lang,
            swap=swap, styles_path=styles_path, preset=preset, position=position,
            fonts_dir=fonts_dir, burn=_bool(options.get("burn")),
            skip_diarize=_bool(options.get("no_diarize")),
        )

        def whole_pipeline(progress):
            produced = run_pipeline(plan, on_progress=lambda stage_name, msg, frac: progress(f"{stage_name}: {msg}", frac))
            return ", ".join(f"{name}={Path(path).name}" for name, path in produced.items())

        return stage, "run the pipeline", whole_pipeline

    raise ApiError(400, f"unknown stage {stage!r}")


# --------------------------------------------------------------------------- #
# request handler
# --------------------------------------------------------------------------- #

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = f"subtitle-studio/{__version__}"
    studio: Studio  # set by the factory

    # ---- plumbing ----------------------------------------------------------

    def log_message(self, fmt: str, *args) -> None:
        """The page has its own log, so requests stay quiet unless asked for:
        STUDIO_DEBUG=1 prints every request to the terminal."""
        if os.environ.get("STUDIO_DEBUG"):
            print(f"  {self.command} {self.path} -> {args[1] if len(args) > 1 else ''}")

    def _guard(self) -> None:
        """Only localhost may talk to this server. A page on the open web can
        POST to 127.0.0.1, so the Host header is checked as well (that is what
        a rebound DNS name would give away)."""
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        if host and host not in LOCAL_HOSTS:
            raise ApiError(403, "this server only answers on localhost")
        client = self.client_address[0] if self.client_address else ""
        if client and client not in {"127.0.0.1", "::1"}:
            raise ApiError(403, f"refused a request from {client}")

    def _send(self, status: int, body: bytes, content_type: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra or {}).items():
            self.send_header(key, str(value))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8", {"Cache-Control": "no-store"})

    def _body(self) -> dict:
        length = _int(self.headers.get("Content-Length"), 0) or 0
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ApiError(400, f"the request body is not valid JSON ({exc})") from None
        return payload if isinstance(payload, dict) else {"value": payload}

    # ---- methods -----------------------------------------------------------

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_HEAD(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_PUT(self) -> None:
        self._dispatch("PUT")

    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        route = parsed.path.rstrip("/") or "/"
        query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
        try:
            self._guard()
            if route == "/api/events" and method == "GET":
                return self._events()
            handler = ROUTES.get((method, route))
            if handler is None:
                if method == "GET":
                    return self._static(parsed.path)
                raise ApiError(404, f"no route for {method} {route}")
            payload = handler(self, query, self._body() if method in {"POST", "PUT"} else {})
            if payload is not None:
                self._json(payload)
        except ApiError as exc:
            self._json({"error": exc.message}, status=exc.status)
        except Busy as exc:
            self._json({"error": str(exc), "busy": True}, status=409)
        except BrokenPipeError:
            pass
        except Exception as exc:
            self._json({"error": f"{type(exc).__name__}: {exc}"}, status=500)

    # ---- server-sent events ------------------------------------------------

    def _events(self) -> None:
        after = _int(parse_qs(urlparse(self.path).query).get("after", ["0"])[-1], 0) or 0
        listener = self.studio.bus.subscribe()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        try:
            for event in self.studio.bus.history(after):
                self._event_line(event)
            while True:
                try:
                    event = listener.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": keep-alive\n\n")  # proxies and browsers both need this
                    self.wfile.flush()
                    continue
                self._event_line(event)
        except (BrokenPipeError, ConnectionResetError, ValueError):
            pass
        finally:
            self.studio.bus.unsubscribe(listener)

    def _event_line(self, event: dict) -> None:
        payload = json.dumps(event, ensure_ascii=False, default=str)
        self.wfile.write(f"id: {event['seq']}\ndata: {payload}\n\n".encode("utf-8"))
        self.wfile.flush()

    # ---- artifacts and the built page --------------------------------------

    def _serve_file(self, path: Path, download: bool = False) -> None:
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if path.suffix in {".ass", ".srt"}:
            content_type = "text/plain; charset=utf-8"
        size = path.stat().st_size
        headers = {"Accept-Ranges": "bytes", "Cache-Control": "no-store"}
        if download:
            headers["Content-Disposition"] = f'attachment; filename="{path.name}"'

        # Range support — a <video> cannot seek a rendered file without it.
        raw_range = self.headers.get("Range")
        start, end = 0, size - 1
        status = 200
        if raw_range and raw_range.startswith("bytes=") and size:
            first, _, last = raw_range[len("bytes=") :].partition("-")
            try:
                if first:
                    start = int(first)
                    end = int(last) if last else size - 1
                else:  # suffix range: the last N bytes
                    start = max(size - int(last), 0)
                if start >= size or start > end:
                    raise ValueError
            except ValueError:
                self._send(416, b"", "text/plain", {"Content-Range": f"bytes */{size}"})
                return
            end = min(end, size - 1)
            status = 206
            headers["Content-Range"] = f"bytes {start}-{end}/{size}"

        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(path, "rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining > 0:
                chunk = handle.read(min(1 << 20, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def _static(self, route: str) -> None:
        dist = self.studio.dist_dir
        if dist is None or not dist.is_dir():
            self._send(
                503,
                (
                    "The page has not been built yet.\n\n"
                    "  cd web && npm install && npm run build\n\n"
                    "or run the Vite dev server with `npm run dev` and open its address.\n"
                ).encode("utf-8"),
                "text/plain; charset=utf-8",
            )
            return
        candidate = (dist / route.lstrip("/")).resolve()
        if not str(candidate).startswith(str(dist.resolve())) or not candidate.is_file():
            candidate = dist / "index.html"  # single page: every other route is the app
        if not candidate.is_file():
            raise ApiError(404, "index.html missing from the build")
        self._serve_file(candidate)


# --------------------------------------------------------------------------- #
# route implementations
# --------------------------------------------------------------------------- #

def route_health(handler: Handler, query: dict, body: dict) -> dict:
    studio = handler.studio
    settings = studio.settings
    styles = styles_info(_input_path(query.get("input"), studio, required=False))
    return {
        "version": __version__,
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "ffprobe": bool(shutil.which("ffprobe")),
        "gpu": _gpu_name(),
        "hf_token": bool(settings.hf_token()),
        "fonts_dir": str(studio.fonts_dir()) if studio.fonts_dir() else None,
        "styles_path": styles["path"],
        "models_dir": settings.paths.models_dir,
        "default_input": str(studio.default_input) if studio.default_input else None,
        "asr_model": settings.asr.model,
        "translation_provider": settings.translation.provider,
        "render_codec": settings.render.codec,
        "built_page": bool(studio.dist_dir and (studio.dist_dir / "index.html").is_file()),
        "uptime_s": round(time.time() - studio.started_at, 1),
    }


def route_browse(handler: Handler, query: dict, body: dict) -> dict:
    raw = query.get("path")
    if raw:
        directory = Path(unquote(raw)).expanduser()
    elif handler.studio.default_input:
        directory = handler.studio.default_input.parent
    else:
        directory = Path.home()
    directory = directory if directory.is_dir() else directory.parent
    if not directory.is_dir():
        raise ApiError(404, f"{directory} is not a directory")
    dirs, files = [], []
    try:
        for entry in sorted(directory.iterdir(), key=lambda p: p.name.lower()):
            if entry.name.startswith("."):
                continue
            try:
                if entry.is_dir():
                    dirs.append({"name": entry.name, "path": str(entry)})
                elif entry.suffix.lower() in MEDIA_SUFFIXES:
                    files.append({"name": entry.name, "path": str(entry), "size": entry.stat().st_size})
            except OSError:
                continue
    except PermissionError:
        raise ApiError(403, f"no permission to read {directory}") from None
    return {
        "path": str(directory),
        "parent": str(directory.parent) if directory.parent != directory else None,
        "home": str(Path.home()),
        "dirs": dirs,
        "files": files,
    }


def route_job(handler: Handler, query: dict, body: dict) -> dict:
    studio = handler.studio
    input_media = _input_path(query.get("input"), studio, required=False)
    state = job_state(input_media, studio.settings, (query.get("track") or "").strip() or None)
    state["job"] = studio.runner.snapshot()
    return state


def route_jobs(handler: Handler, query: dict, body: dict) -> dict:
    return handler.studio.runner.snapshot()


def route_run(handler: Handler, query: dict, body: dict) -> dict:
    stage, label, fn = _stage_job(handler.studio, body)
    job = handler.studio.runner.submit(stage, label, fn)
    return {"job": job.as_dict()}


def route_segment(handler: Handler, query: dict, body: dict) -> dict:
    """Edit one segment's text. Law 1 of the edit-integrity contract: a text
    edit on the source transcript always retimes its words, so the words that
    build the on-screen chunks can never drift from the text. Translated tracks
    carry no word timings by design, so their text is set on its own."""
    from subtitle_studio.schema import load_transcript, retime_words, save_transcript

    studio = handler.studio
    input_media = _input_path(body.get("input"), studio)
    workdir = paths.studio_dir(input_media, None)
    track = (body.get("track") or "").strip() or None
    seg_id = _int(body.get("id"))
    text = " ".join(str(body.get("text", "")).split())
    if seg_id is None:
        raise ApiError(400, "which segment?")
    if not text:
        raise ApiError(400, "a segment cannot be emptied")

    transcript_file = paths.transcript_path(workdir, track)
    if not transcript_file.exists():
        raise ApiError(404, f"{transcript_file.name} not found")
    transcript = load_transcript(transcript_file)
    segment = next((s for s in transcript.segments if s.id == seg_id), None)
    if segment is None:
        raise ApiError(404, f"segment {seg_id} not found")

    segment.text = text
    if not transcript.translated_from:
        segment.words = retime_words(segment, text)
    save_transcript(transcript, transcript_file)
    studio.runner.log(f"segment {seg_id} edited", level="ok")
    studio.bus.publish({"type": "invalidate"})
    return {"id": seg_id, "text": text, "words": len(segment.words)}


def route_speaker(handler: Handler, query: dict, body: dict) -> dict:
    from subtitle_studio.speakers import rename_speaker

    studio = handler.studio
    input_media = _input_path(body.get("input"), studio)
    speaker_id = (body.get("speaker_id") or "").strip()
    name = " ".join(str(body.get("name", "")).split())
    if not speaker_id or not name:
        raise ApiError(400, "a speaker id and a name are required")
    try:
        touched = rename_speaker(paths.studio_dir(input_media, None), speaker_id, name)
    except KeyError as exc:
        raise ApiError(404, str(exc).strip("'")) from None
    studio.runner.log(f"{speaker_id} renamed to {name}", level="ok")
    studio.bus.publish({"type": "invalidate"})
    return {"speaker_id": speaker_id, "name": name, "files": [p.name for p in touched]}


def route_track_remove(handler: Handler, query: dict, body: dict) -> dict:
    """Drop one subtitle track and everything built from it. The source
    transcript is never removable here — losing it would cost a full
    transcription, and no button should be able to do that."""
    studio = handler.studio
    input_media = _input_path(body.get("input"), studio)
    workdir = paths.studio_dir(input_media, None)
    track = (body.get("track") or "").strip()
    if not track:
        raise ApiError(400, "the source transcript cannot be removed from here")

    transcript = paths.transcript_path(workdir, track)
    if not transcript.exists():
        raise ApiError(404, f"no {track} subtitle in this video")

    removed = []
    for candidate in [
        transcript,
        transcript.with_name(transcript.name + ".bak"),
        paths.subs_path(workdir, track),
        paths.render_path(workdir, track),
    ]:
        if candidate.exists():
            candidate.unlink()
            removed.append(candidate.name)

    from subtitle_studio.state import load_state, save_state

    state = load_state(workdir)
    for key in [f"translate:{track}", f"style:{track}", f"render:{track}"]:
        state.get("stages", {}).pop(key, None)
    save_state(workdir, state)

    studio.runner.log(f"{track} subtitle removed ({', '.join(removed)})", level="ok")
    studio.bus.publish({"type": "invalidate"})
    return {"track": track, "removed": removed}


def route_styles_get(handler: Handler, query: dict, body: dict) -> dict:
    studio = handler.studio
    input_media = _input_path(query.get("input"), studio, required=False)
    info = styles_info(
        input_media,
        (query.get("preset") or "").strip() or None,
        (query.get("track") or "").strip() or None,
    )
    info["raw"] = Path(info["path"]).read_text(encoding="utf-8") if info["path"] else ""
    return info


def _styles_file(studio: Studio, raw_input: str | None) -> Path:
    from subtitle_studio.stages.style import project_root, resolve_styles_path

    input_media = _input_path(raw_input, studio, required=False)
    resolved = resolve_styles_path(None, input_media)
    if resolved is not None:
        return resolved
    root = project_root()
    if root is None:
        raise ApiError(404, "no styles.toml to write and no project root to create one in")
    return root / "styles.toml"


def _write_styles(path: Path, text: str) -> None:
    """Validate before replacing: a styles.toml that does not parse would break
    every later stage, and the page would have no way back."""
    import tomllib

    from subtitle_studio.subtitles.styleconf import StyleDef, load_styles

    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ApiError(400, f"that is not valid TOML: {exc}") from None
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    try:
        config = load_styles(tmp)
        StyleDef.model_validate(config.default.model_dump())
        for name in config.preset_names():
            config.base(name)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        raise ApiError(400, f"the styles would not load: {exc}") from None
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + ".bak"))
    os.replace(tmp, path)


def route_styles_put(handler: Handler, query: dict, body: dict) -> dict:
    path = _styles_file(handler.studio, body.get("input"))
    _write_styles(path, str(body.get("raw", "")))
    handler.studio.runner.log(f"{path.name} saved", level="ok")
    handler.studio.bus.publish({"type": "styles"})
    return {"path": str(path)}


def route_styles_set(handler: Handler, query: dict, body: dict) -> dict:
    """Set one key with tomlkit so the file keeps its comments — the styles.toml
    is the documented reference, and a form edit must not strip it."""
    import tomlkit

    path = _styles_file(handler.studio, body.get("input"))
    table_name = (body.get("table") or "default").strip()
    key = (body.get("key") or "").strip()
    if not key:
        raise ApiError(400, "which key?")
    document = tomlkit.parse(path.read_text(encoding="utf-8")) if path.exists() else tomlkit.document()

    container = document
    for part in table_name.split("."):
        if part not in container:
            container[part] = tomlkit.table()
        container = container[part]
    *nested, leaf = key.split(".")
    for part in nested:
        if part not in container:
            container[part] = tomlkit.inline_table()
        container = container[part]
    container[leaf] = body.get("value")

    _write_styles(path, tomlkit.dumps(document))
    handler.studio.bus.publish({"type": "styles"})
    return {"path": str(path), "table": table_name, "key": key, "value": body.get("value")}


def route_styles_preset(handler: Handler, query: dict, body: dict) -> dict:
    import tomlkit

    path = _styles_file(handler.studio, body.get("input"))
    name = (body.get("name") or "").strip()
    action = (body.get("action") or "create").strip()
    if not name:
        raise ApiError(400, "a preset needs a name")
    document = tomlkit.parse(path.read_text(encoding="utf-8")) if path.exists() else tomlkit.document()
    styles = document.setdefault("style", tomlkit.table(is_super_table=True))
    if action == "delete":
        if name in styles:
            del styles[name]
    elif action == "create":
        if name in styles:
            raise ApiError(400, f"preset {name!r} already exists")
        table = tomlkit.table()
        table.comment(f"preset {name} — only the keys that differ from [default]")
        styles[name] = table
    else:
        raise ApiError(400, f"unknown action {action!r}")
    _write_styles(path, tomlkit.dumps(document))
    handler.studio.bus.publish({"type": "styles"})
    return {"path": str(path), "presets": sorted(styles.keys())}


def _combined_subs(
    workdir: Path,
    styles_path: Path | None,
    fonts_dir: Path | None,
    preset: str | None,
    position: str | None,
) -> Path | None:
    """One ASS carrying every built track, or None when there is only one.

    Written to a temp file, NOT into the work directory: `mux` collects tracks
    by globbing `subs.*.ass`, so a preview living there would be muxed in as a
    bogus "preview" language. It is a view, not an artifact — nothing is
    recorded as a stage and nothing downstream goes stale because of it.
    """
    from subtitle_studio.schema import load_transcript
    from subtitle_studio.stages.style import combined_document
    from subtitle_studio.subtitles.styleconf import load_styles, parse_position
    from subtitle_studio.web.status import available_tracks

    tracks = available_tracks(workdir)
    if len(tracks) < 2:
        return None

    transcripts = []
    for entry in tracks:
        path = paths.transcript_path(workdir, entry["id"] or None)
        try:
            transcripts.append(load_transcript(path))
        except Exception:
            continue  # a half-written or older-schema track must not kill the preview
    if len(transcripts) < 2:
        return None

    styles = load_styles(styles_path)
    preset = preset or styles.default_preset
    if position:
        styles.default = styles.default.model_copy(update={"position": parse_position(position)})

    document = combined_document(transcripts, styles, fonts_dir, preset)
    PREVIEW_ASS.write_text(document, encoding="utf-8")
    return PREVIEW_ASS


def route_preview(handler: Handler, query: dict, body: dict) -> None:
    """One PNG, built through the same layout engine that builds the burned
    subtitles (Law 4, preview truth). With a transcript it is a real frame of
    the video at the midpoint of the selected row's FIRST on-screen chunk;
    without one it is the sample-text card over a neutral backdrop."""
    studio = handler.studio
    input_media = _input_path(query.get("input"), studio, required=False)
    track = (query.get("track") or "").strip() or None
    preset = (query.get("preset") or "").strip() or None
    position = (query.get("position") or "").strip() or None
    seg_id = _int(query.get("segment"))
    sample = _bool(query.get("sample"))
    # Every built language at once, the way a video with all of them burned in
    # would look. Defaults on: a page showing one track while the video will
    # carry three is the misleading answer.
    all_tracks = _bool(query.get("all") or "1")
    fonts_dir = studio.fonts_dir()

    with studio.preview_lock:
        from subtitle_studio.stages.style import resolve_styles_path

        styles_path = resolve_styles_path(None, input_media)
        workdir = paths.studio_dir(input_media, None) if input_media else None
        transcript_file = paths.transcript_path(workdir, track) if workdir else None
        live = bool(input_media and transcript_file and transcript_file.exists() and not sample)

        if not live:
            from subtitle_studio.preview import render_style_preview

            png = render_style_preview(
                styles_path, preset=preset, position=position, fonts_dir=fonts_dir,
                out_png=PREVIEW_PNG,
            )
            at, used_segment = None, None
        else:
            from subtitle_studio.schema import load_transcript
            from subtitle_studio.stages.render import escape_filter_path
            from subtitle_studio.stages.style import run_style
            from subtitle_studio.subtitles.layout import segment_events
            from subtitle_studio.subtitles.styleconf import load_styles

            subs = run_style(
                input_media, workdir, lang=track, fonts_dir=fonts_dir,
                preset=preset, position=position,
            )
            transcript = load_transcript(transcript_file)
            target = next((s for s in transcript.segments if s.id == seg_id), None)
            if target is None and transcript.segments:
                target = transcript.segments[0]
            at = (target.start + target.end) / 2 if target else 1.0
            if target is not None:
                config = load_styles(styles_path)
                _, effective = config.resolve(
                    target.speaker, transcript.display_name(target.speaker), preset or config.default_preset
                )
                events = segment_events(target, effective.max_line_chars, effective.max_lines, effective.max_words)
                if events:
                    at = (events[0].start + events[0].end) / 2
            used_segment = target.id if target else None

            overlay = _combined_subs(workdir, styles_path, fonts_dir, preset, position) if all_tracks else None
            vf = f"ass={escape_filter_path(overlay or subs)}"
            if fonts_dir:
                vf += f":fontsdir={escape_filter_path(fonts_dir)}"
            result = subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-ss", f"{at:.3f}", "-copyts", "-i", str(input_media),
                 "-vf", vf, "-frames:v", "1", str(PREVIEW_PNG)],
                capture_output=True, text=True, stdin=subprocess.DEVNULL,
            )
            if result.returncode != 0 or not PREVIEW_PNG.exists():
                raise ApiError(500, f"preview failed: {result.stderr.strip().splitlines()[-1:] or 'ffmpeg error'}")
            png = PREVIEW_PNG

        data = Path(png).read_bytes()

    handler._send(
        200, data, "image/png",
        {
            "Cache-Control": "no-store",
            "X-Preview-At": "" if at is None else f"{at:.3f}",
            "X-Preview-Segment": "" if used_segment is None else str(used_segment),
            "X-Preview-Mode": "frame" if live else "sample",
        },
    )


def route_file(handler: Handler, query: dict, body: dict) -> None:
    """Serve an artifact the page asked for. Only files that belong to a job —
    inside a `.studio/` work directory, next to the input, or the preview PNG."""
    raw = query.get("path")
    if not raw:
        raise ApiError(400, "which file?")
    path = Path(unquote(raw)).expanduser().resolve()
    if not path.is_file():
        raise ApiError(404, f"{path} not found")
    if path.suffix.lower() not in SERVED_SUFFIXES:
        raise ApiError(403, f"{path.suffix} files are not served")

    allowed = path == PREVIEW_PNG.resolve() or any(part.endswith(".studio") for part in path.parts)
    default_input = handler.studio.default_input
    if not allowed and default_input:
        allowed = path.parent == default_input.resolve().parent
    if not allowed:
        requested_input = query.get("input")
        if requested_input:
            allowed = path.parent == Path(unquote(requested_input)).expanduser().resolve().parent
    if not allowed:
        raise ApiError(403, "that file is outside this job")
    handler._serve_file(path, download=_bool(query.get("download")))


ROUTES = {
    ("GET", "/api/health"): route_health,
    ("GET", "/api/browse"): route_browse,
    ("GET", "/api/job"): route_job,
    ("GET", "/api/jobs"): route_jobs,
    ("POST", "/api/run"): route_run,
    ("POST", "/api/segment"): route_segment,
    ("POST", "/api/speaker"): route_speaker,
    ("POST", "/api/track/remove"): route_track_remove,
    ("GET", "/api/styles"): route_styles_get,
    ("PUT", "/api/styles"): route_styles_put,
    ("POST", "/api/styles/set"): route_styles_set,
    ("POST", "/api/styles/preset"): route_styles_preset,
    ("GET", "/api/preview"): route_preview,
    ("GET", "/api/file"): route_file,
}


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #

def build_server(
    input_media: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    dist_dir: Path | None = None,
) -> tuple[ThreadingHTTPServer, Studio]:
    """The server and its shared state, not yet running — `serve` starts it,
    the tests drive it on an ephemeral port."""
    studio = Studio(input_media, dist_dir if dist_dir is not None else default_dist_dir())
    handler_class = type("StudioHandler", (Handler,), {"studio": studio})
    httpd = ThreadingHTTPServer((host, port), handler_class)
    httpd.daemon_threads = True
    return httpd, studio


def serve(
    input_media: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
    dist_dir: Path | None = None,
) -> None:
    httpd, studio = build_server(input_media, host, port, dist_dir)
    url = f"http://{host}:{port}/"

    built = studio.dist_dir and (studio.dist_dir / "index.html").is_file()
    print(f"subtitle-studio web on {url}")
    print(f"  input: {input_media or 'none yet — pick one in the page'}")
    if not built:
        print("  the page is not built yet: cd web && npm install && npm run build")
        print("  (or run `npm run dev` in web/ and open the address it prints)")
    print("  ctrl-c to stop")
    if open_browser and built:
        threading.Timer(0.4, lambda: subprocess.Popen(
            ["xdg-open", url], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
        )).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
