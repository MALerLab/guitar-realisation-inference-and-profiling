"""Serve the GRIP GP viewer: alphaTab draws and plays DadaGP files and optimiser runs, and
annotate mode records how Jae plays a passage (reference passages for calibration).

The server listens on localhost on sym8; VS Code Remote-SSH forwards the port to the desktop.
It serves the page, alphaTab's browser build, a searchable track list from the manifests,
the raw bytes of GP files under the dataset root, and optimiser run files (JSON; the page turns
them into a score) with every note's neck positions. It also runs the optimiser on a passage,
cuts a passage + the source tab's draft for annotating, and saves reference passages.
Settings: configs/gp_viewer/server_v0.1.yaml.

Usage: uv run python -m src.gp_viewer.server [--config PATH]
"""

import argparse
import json
import mimetypes
import traceback
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pandas as pd
import yaml

from src.calibration.reference_set import add_way, is_safe_file_name, reference_file_name, source_tab_draft
from src.optimiser.guitar_neck import GuitarSetup, candidate_positions
from src.optimiser.run_optimiser import (load_run_config, load_source_passage, passage_to_dict, run_search,
                                         save_run_record)

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


def passage_note_positions(passage: dict[str, Any]) -> list[list[dict[str, int]]]:
    """Every neck position the optimiser knows for each note of a passage, in passage order.

    Positions come from the optimiser's own candidate_positions, on the passage's guitar; a null
    symbol (chord, dead note) gets an empty list.

    Args:
        passage: The passage as a run file stores it.
    """
    guitar = passage["guitar"]
    setup = GuitarSetup(tuple(guitar["tuning"]), guitar["highest_fret"], guitar["scale_length_mm"])
    return [
        [] if note["pitch"] is None
        else [{"string": position.string, "fret": position.fret} for position in candidate_positions(note["pitch"], setup)]
        for note in passage["notes"]
    ]


def gp_source_from_request(settings: dict[str, Any], dataset_root: Path, allowed_extensions: list[str]) -> dict[str, Any]:
    """Check the page's passage settings and turn them into a run source (see run_optimiser.load_source_passage).

    Args:
        settings: {"gp", "track", "first_bar", "last_bar", "voice", "tempo_override_bpm" (or null), "tuning_shift"}.
        dataset_root: GP files must sit under this folder.
        allowed_extensions: GP file extensions accepted.

    Raises:
        ValueError: with a message for the page, if anything is missing or out of range.
    """
    gp_path = resolve_inside(dataset_root, str(settings.get("gp", "")))
    if gp_path is None or gp_path.suffix.lower() not in allowed_extensions:
        raise ValueError("no GP file at that path under the dataset root")
    try:
        track, first_bar, last_bar, voice = (int(settings[name]) for name in ("track", "first_bar", "last_bar", "voice"))
        tuning_shift = int(settings.get("tuning_shift") or 0)
        tempo = settings.get("tempo_override_bpm")
        tempo = float(tempo) if tempo not in (None, "") else None
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"passage settings incomplete or not numbers ({error})") from error
    if not 1 <= first_bar <= last_bar:
        raise ValueError(f"bars {first_bar}–{last_bar}: need 1 ≤ first bar ≤ last bar")
    if track < 0 or voice < 0 or (tempo is not None and tempo <= 0):
        raise ValueError("track and voice count from 0; tempo must be positive")
    return {"gp": str(gp_path), "track": track, "bars": f"{first_bar}-{last_bar}", "voice": voice,
            "tempo_override_bpm": tempo, "tuning_shift": tuning_shift}


def guess_content_type(path: Path) -> str:
    """Content type for a served file; falls back to raw bytes."""
    if path.suffix in EXTRA_CONTENT_TYPES:
        return EXTRA_CONTENT_TYPES[path.suffix]
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


class ViewerHandler(BaseHTTPRequestHandler):
    """GET routes: / (page), /run_to_tex.mjs, /alphatab/<file>, /api/config, /api/tracks, /api/file,
    /api/runs, /api/run, /api/positions. POST routes: see do_POST."""

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
        elif url.path == "/api/positions":
            self.send_run_positions(params.get("name", ""))
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
        """Tell the page how alphaTab should read files, where the soundfont is, the Run button's
        default k and where reference passages are saved."""
        alphatab = self.config["alphatab"]
        run_config = load_run_config(self.config["paths"]["optimiser_run_config"])
        self.send_json({
            "text_encoding": alphatab["text_encoding"], "soundfont_url": f"/alphatab/{alphatab['soundfont']}",
            "k_best": run_config["search"]["k_best"],
            "dataset_root": str(self.config["paths"]["dataset_root"].resolve()),
            "reference_set_folder": str(self.config["paths"]["reference_set_folder"]),
        })

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

    def find_run_file(self, name: str) -> Path | None:
        """The run file called `name`, only if it is a .json file directly in the runs folder."""
        runs_folder = self.config["paths"]["runs_folder"]
        path = resolve_inside(runs_folder, name)
        if path is None or path.suffix != ".json" or path.parent != runs_folder.resolve():
            return None
        return path

    def send_run_file(self, name: str) -> None:
        """Send one run file as it is on disk."""
        path = self.find_run_file(name)
        if path is None:
            self.send_error(HTTPStatus.NOT_FOUND, "no run file with that name")
            return
        self.send_file(path)

    def send_run_positions(self, name: str) -> None:
        """Send every note's neck positions for one run file (see run_note_positions)."""
        path = self.find_run_file(name)
        if path is None:
            self.send_error(HTTPStatus.NOT_FOUND, "no run file with that name")
            return
        self.send_json(passage_note_positions(json.loads(path.read_text())["passage"]))

    def do_POST(self) -> None:
        """Routes: /api/optimise, /api/passage, /api/reference. Body and answer are JSON; a refused
        request answers {"error": message} (400 for bad input, 500 for a crash, traceback in the log)."""
        handlers = {"/api/optimise": self.optimise, "/api/passage": self.cut_passage, "/api/reference": self.save_reference}
        handler = handlers.get(urlparse(self.path).path)
        if handler is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            self.send_json(handler(body))
        except ValueError as error:
            self.send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
        except Exception as error:  # noqa: BLE001 — any crash goes back to the page as one line
            traceback.print_exc()
            self.send_json({"error": f"{type(error).__name__}: {error}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def gp_source(self, settings: dict[str, Any]) -> dict[str, Any]:
        """The page's passage settings as a checked run source (see gp_source_from_request)."""
        return gp_source_from_request(settings, self.config["paths"]["dataset_root"],
                                      self.config["gp_files"]["allowed_extensions"])

    def optimise(self, body: dict[str, Any]) -> dict[str, Any]:
        """Run the optimiser on a passage and save the run (always); answers the run file's name.

        Args:
            body: Passage settings (see gp_source_from_request) plus "k_best" (null = run config's).
        """
        run_config_path = self.config["paths"]["optimiser_run_config"]
        k_best = int(body["k_best"]) if body.get("k_best") not in (None, "") else None
        _, record = run_search(self.gp_source(body), k_best, comment=None, run_config_path=run_config_path)
        return {"name": save_run_record(record, run_config_path).name}

    def cut_passage(self, body: dict[str, Any]) -> dict[str, Any]:
        """Cut a passage out of a GP file for annotating, without searching.

        Answers the source, the passage (as run files store it), every note's positions, the source
        tab's own string / fret / finger / stroke as the draft, and report lines.

        Args:
            body: Passage settings (see gp_source_from_request).
        """
        run_config_path = self.config["paths"]["optimiser_run_config"]
        source = self.gp_source(body)
        passage = passage_to_dict(load_source_passage(source, run_config_path))
        draft, draft_report = source_tab_draft(source, passage, load_run_config(run_config_path)["gp_parser_config"])
        return {"source": source, "passage": passage, "positions": passage_note_positions(passage),
                "draft": draft, "report": passage["report"] + draft_report}

    def save_reference(self, body: dict[str, Any]) -> dict[str, Any]:
        """Add one way to a reference passage file (or only check it, with "dry_run": true).

        The passage is rebuilt from the source here, so the file never trusts the page's copy.

        Args:
            body: {"file_name", "settings" (passage settings), "way": {"started_from", "comment",
                "choices"}, "dry_run"}.
        """
        file_name = str(body.get("file_name", ""))
        if not is_safe_file_name(file_name):
            raise ValueError("file name: lowercase letters, digits, _ and - only, ending in .json")
        source = self.gp_source(body["settings"])
        passage = passage_to_dict(load_source_passage(source, self.config["paths"]["optimiser_run_config"]))
        path = self.config["paths"]["reference_set_folder"] / file_name
        existed = path.exists()
        way_number = add_way(path, source, passage, body["way"], dry_run=bool(body.get("dry_run")))
        return {"file_name": file_name, "way_number": way_number, "file_existed": existed}

    def send_file(self, path: Path) -> None:
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", guess_content_type(path))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
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
