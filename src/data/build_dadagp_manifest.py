"""Build the DadaGP manifest: one row per song, one row per guitar track. Indexes and counts only.

Reads the ORIGINAL gp3/gp4/gp5 file of each song (not the tokens, which rewrite drop tunings),
via alphaTab (src/data/alphatab_track_metadata_dump.mjs). Settings: configs/data/build_dadagp_manifest_v*.yaml.

Usage: uv run python -m src.data.build_dadagp_manifest [--config PATH] [--sample-size N] [--output-dir DIR]
"""

import argparse
import html
import json
import random
import re
import urllib.parse
from dataclasses import dataclass
from functools import partial
from multiprocessing import Pool
from pathlib import Path
from typing import Any

import nodejs_wheel
import pandas as pd
import yaml

from src.data.gp_parser import detect_gp_format

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "configs/data/build_dadagp_manifest_v0.1.yaml"

# Every DadaGP song has exactly one tokens file, named <original file>.tokens.txt
TOKENS_SUFFIX = ".tokens.txt"

# Patterns that suggest a title is still garbled after the exact fixes (approximate by design)
GARBLE_PATTERNS = [
    re.compile(r"_"),  # a lost character: Caf_, Why_, 27_12_1937
    re.compile(r"\b[A-Z]{2}[a-z]"),  # accent → two capitals at word start: DCsir, MArchen, SUng
    re.compile(r"[a-z][A-Z]{1,2}[a-z]{2}"),  # accent → capitals mid-word: PerlPSdio, EspaSSola, KNmpa
    re.compile(r"[a-z][A-Z]\b"),  # accent → capital at word end: VedN
    re.compile(r"[A-Za-z],[a-z]"),  # é → comma inside a word: D,sir, F,lix
    re.compile(r"[A-Za-z]%[0-9A-Fa-f]"),  # ç → %: Lia%0es
]


@dataclass(frozen=True)
class ManifestConfig:
    """Settings of the DadaGP manifest build, loaded from configs/data/build_dadagp_manifest_v*.yaml.

    Args:
        version: Config version, e.g. "0.1".
        dataset_root: DadaGP v1.1 root folder.
        output_dir: Folder the two parquet files are written to.
        songs_file: File name of the song table.
        tracks_file: File name of the guitar-track table.
        node_script: Absolute path to the alphaTab track metadata dump script.
        text_encoding: How alphaTab decodes stored text such as track names.
        timeout_seconds: Seconds before one file's Node run is abandoned.
        worker_count: Files read in parallel.
        sample_seed: Seed for picking a random subset of songs.
        guitar_midi_programs: MIDI programs that count as guitar unless the name says bass.
        bass_midi_programs: MIDI programs where a guitar word in the name does not rescue a track.
        name_alternative_encodings: Extra readings of a name's bytes (e.g. cp1251) searched for words.
        guitar_name_pattern: Words in a track name that say guitar.
        bass_name_pattern: Words in a track name that say bass.
        standard_tunings: Standard tuning per string count, highest string first.
        max_abs_shift_semitones: Largest shared shift still treated as a real retuning.
        drop_semitones: How far below the shared shift the lowest string sits in a drop tuning.
    """

    version: str
    dataset_root: Path
    output_dir: Path
    songs_file: str
    tracks_file: str
    node_script: Path
    text_encoding: str
    timeout_seconds: float
    worker_count: int
    sample_seed: int
    guitar_midi_programs: frozenset[int]
    bass_midi_programs: frozenset[int]
    name_alternative_encodings: tuple[str, ...]
    guitar_name_pattern: re.Pattern[str]
    bass_name_pattern: re.Pattern[str]
    standard_tunings: dict[int, tuple[int, ...]]
    max_abs_shift_semitones: int
    drop_semitones: int


@dataclass(frozen=True)
class TuningDescription:
    """A tuning compared with standard tuning for its string count.

    Args:
        string_offsets: Semitones from standard per string, highest string first; None without a reference.
        tuning_class: "standard", "uniform_shift", "drop" or "other".
        shift_semitones: Shift shared by all strings (all but the lowest, for a drop); None for "other".
    """

    string_offsets: tuple[int, ...] | None
    tuning_class: str
    shift_semitones: int | None


def load_manifest_config(config_path: Path) -> ManifestConfig:
    """Load the manifest build config.

    Args:
        config_path: Path to a configs/data/build_dadagp_manifest_v*.yaml file.
    """
    raw = yaml.safe_load(Path(config_path).read_text())
    return ManifestConfig(
        version=str(raw["version"]),
        dataset_root=Path(raw["paths"]["dataset_root"]).expanduser(),
        output_dir=REPO_ROOT / raw["paths"]["output_dir"],
        songs_file=raw["paths"]["songs_file"],
        tracks_file=raw["paths"]["tracks_file"],
        node_script=REPO_ROOT / raw["runtime"]["node_script"],
        text_encoding=raw["runtime"]["text_encoding"],
        timeout_seconds=float(raw["runtime"]["timeout_seconds"]),
        worker_count=int(raw["runtime"]["worker_count"]),
        sample_seed=int(raw["runtime"]["sample_seed"]),
        guitar_midi_programs=frozenset(raw["guitar_tracks"]["midi_programs"]),
        bass_midi_programs=frozenset(raw["guitar_tracks"]["bass_midi_programs"]),
        name_alternative_encodings=tuple(raw["guitar_tracks"]["name_alternative_encodings"]),
        guitar_name_pattern=re.compile(raw["guitar_tracks"]["guitar_name_pattern"]),
        bass_name_pattern=re.compile(raw["guitar_tracks"]["bass_name_pattern"]),
        standard_tunings={
            int(string_count): tuple(tuning)
            for string_count, tuning in raw["tunings"]["standard_by_string_count"].items()
        },
        max_abs_shift_semitones=int(raw["tunings"]["max_abs_shift_semitones"]),
        drop_semitones=int(raw["tunings"]["drop_semitones"]),
    )


def list_song_paths(dataset_root: Path) -> list[str]:
    """List every song's original GP file, as a path relative to the dataset root, sorted.

    Args:
        dataset_root: DadaGP v1.1 root folder.
    """
    return sorted(
        str(tokens_path.relative_to(dataset_root))[: -len(TOKENS_SUFFIX)]
        for tokens_path in dataset_root.glob(f"*/*/*{TOKENS_SUFFIX}")
    )


def run_track_metadata_dump(gp_path: Path, config: ManifestConfig) -> list[dict[str, Any]]:
    """Run the Node dump script on one file and return one dict per staff.

    Args:
        gp_path: Path to the Guitar Pro file.
        config: Loaded manifest config (script path, text encoding, timeout).
    """
    completed = nodejs_wheel.node(
        [str(config.node_script), str(gp_path), config.text_encoding],
        return_completed_process=True,
        capture_output=True,
        text=True,
        timeout=config.timeout_seconds,
        cwd=REPO_ROOT,
    )
    if completed.returncode != 0:
        # Keep the error line itself, not the stack trace around it
        error_lines = [line for line in completed.stderr.splitlines() if "Error" in line]
        raise RuntimeError(f"alphaTab failed: {(error_lines or [completed.stderr.strip()])[-1].strip()}")
    return [json.loads(line) for line in completed.stdout.splitlines()]


def describe_tuning(tuning: tuple[int, ...], config: ManifestConfig) -> TuningDescription:
    """Compare a tuning with standard tuning for its string count and label its shape.

    Args:
        tuning: Open-string MIDI pitches, highest string first.
        config: Loaded manifest config (standard tunings, shift limit, drop size).
    """
    standard = config.standard_tunings.get(len(tuning))
    if standard is None:
        return TuningDescription(string_offsets=None, tuning_class="other", shift_semitones=None)
    offsets = tuple(pitch - standard_pitch for pitch, standard_pitch in zip(tuning, standard))

    # Shift shared by every string except the lowest; the lowest decides uniform vs drop
    shared_shift = offsets[0]
    upper_strings_shared = all(offset == shared_shift for offset in offsets[:-1])
    plausible_shift = abs(shared_shift) <= config.max_abs_shift_semitones
    if upper_strings_shared and plausible_shift:
        if offsets[-1] == shared_shift:
            tuning_class = "standard" if shared_shift == 0 else "uniform_shift"
            return TuningDescription(offsets, tuning_class, shared_shift)
        if offsets[-1] == shared_shift - config.drop_semitones:
            return TuningDescription(offsets, "drop", shared_shift)
    return TuningDescription(offsets, "other", None)


def clean_title(file_stem: str) -> str:
    """Apply the exact name fixes to a file stem (no guessing of garbled letters).

    Fixes: numeric HTML entities (&#367;), URL encoding (only when %20 shows the name is
    URL-encoded), "_" before an apostrophe (Don_'t → Don't), and repeated or edge whitespace.

    Args:
        file_stem: File name without the .gp3/.gp4/.gp5 extension.
    """
    text = re.sub(r"&#(\d+);", lambda match: chr(int(match.group(1))), file_stem)
    if "%20" in text:
        text = decode_url_encoding(text)
    text = re.sub(r"_+'", "'", text)
    return re.sub(r"\s+", " ", text).strip()


def decode_url_encoding(text: str) -> str:
    """Decode %XX sequences, as UTF-8 when valid, else as Latin-1 (e.g. %F1 = ñ).

    Args:
        text: A URL-encoded name.
    """
    try:
        return urllib.parse.unquote(text, encoding="utf-8", errors="strict")
    except UnicodeDecodeError:
        return urllib.parse.unquote(text, encoding="latin-1")


def split_title(cleaned_stem: str) -> str:
    """Return the title part of "<artist> - <title>"; the artist itself comes from the folder.

    Falls back to a bare hyphen ("Band-Title"), then to the whole name.

    Args:
        cleaned_stem: File stem after clean_title.
    """
    if " - " in cleaned_stem:
        return cleaned_stem.split(" - ", 1)[1].strip()
    bare_hyphen = re.match(r"^(.+?)\s?-\s?(.+)$", cleaned_stem)
    if bare_hyphen:
        return bare_hyphen.group(2).strip()
    return cleaned_stem


def is_possibly_garbled(title: str) -> bool:
    """True if the title still shows a sign of lost or mangled characters (approximate).

    Args:
        title: Display title after the exact fixes.
    """
    return any(pattern.search(title) for pattern in GARBLE_PATTERNS)


def version_group_key(artist: str, title: str) -> str:
    """Key shared by copies of one song: artist + title, ignoring case, punctuation, "_" and a "(N)" suffix.

    Other bracket words, e.g. "(Solo)" or "(intro)", stay in the key: they usually mark a different part.

    Args:
        artist: Artist folder name.
        title: Display title.
    """
    title_without_copy_number = re.sub(r"\s*\(\d+\)\s*$", "", title)

    def normalise(text: str) -> str:
        return re.sub(r"[^0-9a-z]+", " ", text.lower()).strip()

    return f"{normalise(artist)} | {normalise(title_without_copy_number)}"


def build_song(song_path: str, config: ManifestConfig) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Read one song and return its song row and its guitar-track rows.

    Args:
        song_path: Original GP file, relative to the dataset root.
        config: Loaded manifest config.
    """
    artist_folder = Path(song_path).parent.name
    file_stem = re.sub(r"\.gp[345]$", "", Path(song_path).name, flags=re.IGNORECASE)
    title = split_title(clean_title(file_stem))
    song_row: dict[str, Any] = {
        "path": song_path,
        "format": None,
        "artist": artist_folder,
        "title_display": title,
        "name_garbled": is_possibly_garbled(title),
        "version_group": version_group_key(artist_folder, title),
        "track_count": None,
        "guitar_track_count": None,
        "parse_error": None,
    }

    # Any failure keeps the song row, records why, and yields no track rows
    gp_path = config.dataset_root / song_path
    try:
        song_row["format"] = detect_gp_format(gp_path)
        staff_rows = run_track_metadata_dump(gp_path, config)
        track_rows = []
        for staff_row in staff_rows:
            identified_by = guitar_evidence(staff_row, config)
            if identified_by is not None:
                track_rows.append(build_track_row(song_path, staff_row, identified_by, config))
    except Exception as error:  # noqa: BLE001 — every failure is recorded, none stops the build
        song_row["parse_error"] = f"{type(error).__name__}: {error}"[:500]
        return song_row, []

    song_row["track_count"] = len(staff_rows)
    song_row["guitar_track_count"] = len(track_rows)
    return song_row, track_rows


def guitar_evidence(staff_row: dict[str, Any], config: ManifestConfig) -> str | None:
    """Say why a staff counts as guitar ("midi_program" or "track_name"), or None if it doesn't.

    Guitar program → guitar, unless the name says bass. Other program → guitar only if the name says
    guitar (and not bass), and the program is not a bass.

    Args:
        staff_row: One row from the track metadata dump.
        config: Loaded manifest config (MIDI program families, name patterns).
    """
    if staff_row["isPercussion"] or len(staff_row["tuning"]) == 0:
        return None
    name = searchable_name(staff_row["trackName"], config.name_alternative_encodings)
    says_bass = config.bass_name_pattern.search(name) is not None
    says_guitar = config.guitar_name_pattern.search(name) is not None
    program = staff_row["midiProgram"]
    if program in config.guitar_midi_programs:
        return None if says_bass else "midi_program"
    if says_guitar and not says_bass and program not in config.bass_midi_programs:
        return "track_name"
    return None


def searchable_name(track_name: str, alternative_encodings: tuple[str, ...]) -> str:
    """Lowercased track name plus its re-readings in other alphabets, for word search.

    gp3–5 do not record the alphabet: a Russian "Гитара" arrives as "Ãèòàðà" when decoded as
    windows-1252. Re-encoding to windows-1252 and decoding as cp1251 recovers it.

    Args:
        track_name: Name as decoded by alphaTab (windows-1252).
        alternative_encodings: Code pages to re-read the name's bytes with, e.g. ("cp1251", "cp1255").
    """
    readings = [track_name]
    try:
        name_bytes = track_name.encode("cp1252")
    except UnicodeEncodeError:  # a byte windows-1252 leaves undefined; skip the re-readings
        name_bytes = None
    if name_bytes is not None:
        readings += [name_bytes.decode(encoding, errors="ignore") for encoding in alternative_encodings]
    return " ".join(readings).lower()


def build_track_row(
    song_path: str, staff_row: dict[str, Any], identified_by: str, config: ManifestConfig
) -> dict[str, Any]:
    """Turn one dumped guitar staff into a manifest track row.

    Args:
        song_path: Original GP file, relative to the dataset root.
        staff_row: One row from the track metadata dump.
        identified_by: Why the staff counts as guitar: "midi_program" or "track_name".
        config: Loaded manifest config (tuning references).
    """
    # gp3–5 have one staff per track, so track_index alone identifies the track
    if staff_row["staffIndex"] != 0:
        raise ValueError(f"unexpected second staff in track {staff_row['trackIndex']}")
    tuning = tuple(staff_row["tuning"])
    tuning_description = describe_tuning(tuning, config)
    return {
        "path": song_path,
        "track_index": staff_row["trackIndex"],
        "track_name": staff_row["trackName"],
        "midi_program": staff_row["midiProgram"],
        "guitar_identified_by": identified_by,
        "string_count": len(tuning),
        "tuning": list(tuning),
        "string_offsets": (
            list(tuning_description.string_offsets) if tuning_description.string_offsets is not None else None
        ),
        "tuning_class": tuning_description.tuning_class,
        "shift_semitones": tuning_description.shift_semitones,
        "capo": staff_row["capo"],
        "note_count": staff_row["noteCount"],
        "pick_stroke_beat_count": staff_row["pickStrokeBeatCount"],
    }


def choose_song_paths(all_song_paths: list[str], sample_size: int | None, seed: int) -> list[str]:
    """Return every song, or a seeded random subset in sorted order.

    Args:
        all_song_paths: Every song path, sorted.
        sample_size: Number of songs to keep; None keeps all.
        seed: Random seed for the subset.
    """
    if sample_size is None or sample_size >= len(all_song_paths):
        return all_song_paths
    return sorted(random.Random(seed).sample(all_song_paths, sample_size))


def build_manifest(song_paths: list[str], config: ManifestConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read every song in parallel and return the song table and the guitar-track table.

    Args:
        song_paths: Songs to read, relative to the dataset root.
        config: Loaded manifest config.
    """
    with Pool(config.worker_count) as pool:
        results = pool.map(partial(build_song, config=config), song_paths, chunksize=20)
    song_rows = [song_row for song_row, _ in results]
    track_rows = [track_row for _, song_track_rows in results for track_row in song_track_rows]
    songs = pd.DataFrame(song_rows).astype({"track_count": "Int64", "guitar_track_count": "Int64"})
    tracks = pd.DataFrame(track_rows).astype({"shift_semitones": "Int64"})
    return songs, tracks


def main() -> None:
    """Build the manifest from the command line and write the two parquet files."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--sample-size", type=int, default=None, help="random subset of songs, for prototyping")
    parser.add_argument("--output-dir", type=Path, default=None, help="overrides paths.output_dir")
    arguments = parser.parse_args()

    config = load_manifest_config(arguments.config)
    song_paths = choose_song_paths(list_song_paths(config.dataset_root), arguments.sample_size, config.sample_seed)
    songs, tracks = build_manifest(song_paths, config)

    # Write both tables side by side
    output_dir = arguments.output_dir or config.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    songs.to_parquet(output_dir / config.songs_file, index=False)
    tracks.to_parquet(output_dir / config.tracks_file, index=False)
    print(f"{len(songs)} songs ({songs['parse_error'].notna().sum()} failed), {len(tracks)} guitar tracks → {output_dir}")


if __name__ == "__main__":
    main()
