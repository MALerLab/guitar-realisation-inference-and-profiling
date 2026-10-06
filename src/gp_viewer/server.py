"""Serve a minimal Guitar Pro viewer: alphaTab draws and plays DadaGP files and optimiser runs.

The server listens on localhost on sym8; VS Code Remote-SSH forwards the port to the desktop.
It serves the page, alphaTab's browser build, a searchable track list from the manifests,
the raw bytes of GP files under the dataset root, and optimiser run files (JSON; the page turns
them into a score). Settings: configs/gp_viewer/server_v0.1.yaml.

Usage: uv run python -m src.gp_viewer.server [--config PATH]
"""

import argparse
import json
import mimetypes
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "configs/gp_viewer/server_v0.1.yaml"
PAGE_FILE = Path(__file__).resolve().parent / "index.html"
# The page's run file → alphaTex converter (an ES module the page imports)
RUN_TO_TEX_FILE = Path(__file__).resolve().parent / "run_to_tex.mjs"

# Columns the page's track list shows; song-level ones come from the songs manifest
TRACK_COLUMNS = ["path", "track_index", "track_name", "guitar_or_bass", "name_says_vocal_or_melody"]
SONG_COLUMNS = ["path", "artist", "title_display", "parse_error"]

# Types Python's mimetypes table may lack for alphaTab's files
EXTRA_CONTENT_TYPES = {
    ".mjs": "text/javascript",
    ".sf2": "application/octet-stream",
    ".sf3": "application/octet-stream",
    ".woff2": "font/woff2",
}


def resolve_config_path(value: str) -> Path:
    """Turn a config path into an absolute path: ~ expanded, relative paths taken from the repo root."""
    path = Path(value).expanduser()
    return path if path.is_absolute() else REPO_ROOT / path


def load_config(config_path: Path) -> dict[str, Any]:
    """Read the viewer config and resolve its paths.

    Args:
        config_path: YAML file with server, paths, alphatab and track_list sections.
    """
    config = yaml.safe_load(config_path.read_text())
    config["paths"] = {name: resolve_config_path(value) for name, value in config["paths"].items()}
    return config


def load_track_table(tracks_manifest: Path, songs_manifest: Path) -> pd.DataFrame:
    """Join the tracks manifest with song-level columns, plus one lowercase search string per row."""
    tracks = pd.read_parquet(tracks_manifest, columns=TRACK_COLUMNS)
    songs = pd.read_parquet(songs_manifest, columns=SONG_COLUMNS)
    table = tracks.merge(songs, on="path", how="left")
    # One string to substring-match against: artist, title, track name, path
    table["search_text"] = (
        table[["artist", "title_display", "track_name", "path"]].fillna("").agg(" ".join, axis=1).str.lower()
    )
    return table


def search_tracks(table: pd.DataFrame, query: str, vocal_or_melody_only: bool, max_rows: int) -> dict[str, Any]:
    """Filter the track table by words in `query` (all must match) and the vocal/melody flag.

    Args:
        table: output of load_track_table.
        query: space-separated words, matched case-insensitively.
        vocal_or_melody_only: keep only tracks whose name says vocal or melody.
        max_rows: most rows returned; the total match count is reported separately.
    """
    matches = table
    if vocal_or_melody_only:
        matches = matches[matches["name_says_vocal_or_melody"]]
    for word in query.lower().split():
        matches = matches[matches["search_text"].str.contains(word, regex=False)]
    rows = matches.drop(columns="search_text").head(max_rows)
    # Missing values (e.g. no parse_error) become JSON null
    rows = rows.astype(object).where(rows.notna(), None)
    return {"total": len(matches), "rows": rows.to_dict(orient="records")}


def resolve_inside(root: Path, requested: str) -> Path | None:
    """Resolve `requested` (relative to `root`, or absolute) and return it only if it stays inside `root`."""
    requested_path = Path(requested).expanduser()
    candidate = requested_path if requested_path.is_absolute() else root / requested_path
    candidate = candidate.resolve()
    return candidate if candidate.is_relative_to(root.resolve()) and candidate.is_file() else None


def guess_content_type(path: Path) -> str:
    """Content type for a served file; falls back to raw bytes."""
    if path.suffix in EXTRA_CONTENT_TYPES:
        return EXTRA_CONTENT_TYPES[path.suffix]
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


class ViewerHandler(BaseHTTPRequestHandler):
    """Routes: / (page), /run_to_tex.mjs, /alphatab/<file>, /api/config, /api/tracks, /api/file,
    /api/runs, /api/run."""

    def __init__(self, *args: Any, config: dict[str, Any], track_table: pd.DataFrame, **kwargs: Any):
        self.config = config
        self.track_table = track_table
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:
        url = urlparse(self.path)
        params = {name: values[0] for name, values in parse_qs(url.query).items()}
        if url.path in ("/", "/index.html"):
            self.send_file(PAGE_FILE)
        elif url.path == "/run_to_tex.mjs":
            self.send_file(RUN_TO_TEX_FILE)
        elif url.path.startswith("/alphatab/"):
            self.send_alphatab_file(url.path.removeprefix("/alphatab/"))
        elif url.path == "/api/config":
            self.send_page_config()
        elif url.path == "/api/tracks":
            self.send_track_search(params)
        elif url.path == "/api/file":
            self.send_gp_file(params.get("path", ""))
        elif url.path == "/api/runs":
            self.send_run_list()
        elif url.path == "/api/run":
            self.send_run_file(params.get("name", ""))
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def send_alphatab_file(self, relative_path: str) -> None:
        """Serve one file from alphaTab's dist folder (script, worker, font, soundfont)."""
        path = resolve_inside(self.config["paths"]["alphatab_dist"], relative_path)
        if path is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.send_file(path)

    def send_page_config(self) -> None:
        """Tell the page how alphaTab should read files and where the soundfont is."""
        alphatab = self.config["alphatab"]
        self.send_json({"text_encoding": alphatab["text_encoding"], "soundfont_url": f"/alphatab/{alphatab['soundfont']}"})

    def send_track_search(self, params: dict[str, str]) -> None:
        """Return manifest tracks matching the page's search box and vocal/melody toggle."""
        result = search_tracks(
            self.track_table,
            query=params.get("query", ""),
            vocal_or_melody_only=params.get("vocal_or_melody_only") == "1",
            max_rows=self.config["track_list"]["max_rows"],
        )
        self.send_json(result)

    def send_gp_file(self, requested: str) -> None:
        """Send one GP file's bytes, only if it sits under the dataset root and has a GP extension."""
        path = resolve_inside(self.config["paths"]["dataset_root"], requested)
        if path is None or path.suffix.lower() not in self.config["gp_files"]["allowed_extensions"]:
            self.send_error(HTTPStatus.NOT_FOUND, "no GP file at that path under the dataset root")
            return
        self.send_file(path)

    def send_run_list(self) -> None:
        """List the run files, newest first (by modification time)."""
        runs_folder = self.config["paths"]["runs_folder"]
        runs = sorted(runs_folder.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        self.send_json([path.name for path in runs])

    def send_run_file(self, name: str) -> None:
        """Send one run file, only if it is a .json file directly in the runs folder."""
        path = resolve_inside(self.config["paths"]["runs_folder"], name)
        if path is None or path.suffix != ".json" or path.parent != self.config["paths"]["runs_folder"].resolve():
            self.send_error(HTTPStatus.NOT_FOUND, "no run file with that name")
            return
        self.send_file(path)

    def send_file(self, path: Path) -> None:
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", guess_content_type(path))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload: Any) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()

    # Load config and the track table once; every request reuses them
    config = load_config(args.config)
    track_table = load_track_table(config["paths"]["tracks_manifest"], config["paths"]["songs_manifest"])
    handler = partial(ViewerHandler, config=config, track_table=track_table)

    host, port = config["server"]["host"], config["server"]["port"]
    server = ThreadingHTTPServer((host, port), handler)
    print(f"GP viewer: {len(track_table)} tracks loaded, serving http://{host}:{port} (Ctrl-C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
