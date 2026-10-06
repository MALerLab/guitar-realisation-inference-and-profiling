"""Reference passages: how Jae plays a passage, the answer key the cost knobs are fitted to.

One JSON file per passage (format grip_reference_passage). It holds where the passage comes from
(the same source fields as an optimiser run), a snapshot of the passage's notes, and one or more
ways: several equally good ways to play it. A way gives, per note:
- string + fret: required for every playable note (null for a null symbol)
- finger: 0 = open, 1–4 = index … pinky, null = don't care
- stroke: "down", "up", "none" (no pick: hammer-on, pull-off, slide, tap), null = don't care

Also builds the draft an annotation starts from when it starts from the source tab: the tab's
own string, fret, finger and pick-stroke marks. This is the reference side only; the source
tab's fingering still never enters generation.

Imports src/optimiser/, never the reverse.
"""

import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from src.data.gp_parser import load_gp_parser_config, parse_gp_file_with_tempo
from src.optimiser.guitar_neck import GuitarSetup, candidate_positions

REFERENCE_FILE_FORMAT = {"name": "grip_reference_passage", "version": "0.1"}
STROKES = ("down", "up", "none")
# Parser finger names → finger numbers (thumb isn't in the optimiser's model → don't care)
SOURCE_FINGERS = {"index": 1, "middle": 2, "annular": 3, "little": 4}
# Passage articulations that mean the note isn't picked
NO_PICK_ARTICULATIONS = {"legato", "slide", "left_hand_tap"}
# Note fields that must match for a way to belong to a passage
SNAPSHOT_NOTE_FIELDS = ("pitch", "onset_tick", "duration_tick", "articulations", "null_reason")


def reference_file_name(passage_name: str) -> str:
    """Suggested file name for a passage: lowercase words joined by _, e.g. "song_track_0_bars_17_28.json".

    Args:
        passage_name: The passage's name.
    """
    return re.sub(r"[^a-z0-9]+", "_", passage_name.lower()).strip("_") + ".json"


def is_safe_file_name(file_name: str) -> bool:
    """True for a plain file name of lowercase letters, digits, _ and - ending in .json."""
    return re.fullmatch(r"[a-z0-9_\-]+\.json", file_name) is not None


def source_tab_draft(source: dict[str, Any], passage: dict[str, Any],
                     gp_parser_config_path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """The source tab's own string, fret, finger and pick stroke for each note of a GP passage.

    The passage groups the tab's notes by start time (see note_input.gp_events_to_notes), so each
    passage note is found again by its onset tick. Frets are recomputed on the passage's guitar
    (string kept): with a tuning shift the same pitch sits at another fret. A note whose string
    can't reach the pitch gets no position, to be picked by hand.

    Args:
        source: A GP run source: "gp", "track", "bars" ("5-8"), "voice".
        passage: The passage as a run file stores it (see run_optimiser.passage_to_dict).
        gp_parser_config_path: The run config's GP parser config.

    Returns:
        One choice per passage note, and report lines about notes needing attention.
    """
    events, _ = parse_gp_file_with_tempo(Path(source["gp"]), load_gp_parser_config(gp_parser_config_path))
    first_bar, last_bar = (int(bar) for bar in source["bars"].split("-"))
    events_by_onset = defaultdict(list)
    for event in events:
        if (event.track_index == source["track"] and event.staff_index == 0 and event.voice_index == source["voice"]
                and first_bar - 1 <= event.bar_index <= last_bar - 1):
            events_by_onset[event.onset_tick].append(event)

    tuning = passage["guitar"]["tuning"]
    highest_fret = passage["guitar"]["highest_fret"]
    choices, needs_position = [], []
    for index, note in enumerate(passage["notes"]):
        choice = {"passage_index": index, "string": None, "fret": None, "finger": None, "stroke": None}
        group = events_by_onset.get(note["onset_tick"], [])
        if note["pitch"] is not None and len(group) == 1:
            event = group[0]
            fret = note["pitch"] - tuning[event.string - 1]
            if 0 <= fret <= highest_fret:
                choice.update(string=event.string, fret=fret)
                choice["finger"] = 0 if fret == 0 else SOURCE_FINGERS.get(event.left_hand_finger)
                choice["stroke"] = source_stroke(event.techniques, note["articulations"])
            else:
                needs_position.append(index + 1)
        choices.append(choice)
    report = [f"notes {needs_position}: the tab's string can't play the pitch → pick a position"] if needs_position else []
    return choices, report


def source_stroke(techniques: tuple[str, ...], articulations: list[str]) -> str | None:
    """The tab's stroke for one note: its pick-stroke mark, "none" for legato / slide / tap, else don't care.

    Args:
        techniques: The note's technique tags from the parser.
        articulations: The passage note's articulations (a slide's landing note is marked here,
            not in its own tags).
    """
    if "pick_stroke_down" in techniques:
        return "down"
    if "pick_stroke_up" in techniques:
        return "up"
    if NO_PICK_ARTICULATIONS & set(articulations):
        return "none"
    return None


def passage_snapshot(passage: dict[str, Any]) -> dict[str, Any]:
    """The parts of a passage a way depends on: name, tempo, guitar and each note's timing + pitch.

    Args:
        passage: The passage as a run file stores it.
    """
    notes = [{field: note[field] for field in ("passage_index", *SNAPSHOT_NOTE_FIELDS, "bar_start")}
             for note in passage["notes"]]
    snapshot = {"name": passage["name"], "tempo_bpm": passage["tempo_bpm"], "guitar": passage["guitar"], "notes": notes}
    # Through JSON and back, so it compares equal to a snapshot read from a file (tuples become lists)
    return json.loads(json.dumps(snapshot))


def same_passage(snapshot_a: dict[str, Any], snapshot_b: dict[str, Any]) -> bool:
    """True if two snapshots have the same guitar tuning and the same notes (pitch + timing + marks)."""
    if snapshot_a["guitar"]["tuning"] != snapshot_b["guitar"]["tuning"] or len(snapshot_a["notes"]) != len(snapshot_b["notes"]):
        return False
    return all(all(a[field] == b[field] for field in SNAPSHOT_NOTE_FIELDS)
               for a, b in zip(snapshot_a["notes"], snapshot_b["notes"]))


def way_problems(passage: dict[str, Any], choices: list[dict[str, Any]]) -> list[str]:
    """Everything wrong with one way, as lines for Jae; an empty list means it can be saved.

    Args:
        passage: The passage as a run file stores it.
        choices: One choice per passage note (string, fret, finger, stroke).
    """
    notes = passage["notes"]
    if len(choices) != len(notes):
        return [f"{len(choices)} choices for {len(notes)} notes"]
    guitar = passage["guitar"]
    setup = GuitarSetup(tuple(guitar["tuning"]), guitar["highest_fret"], guitar["scale_length_mm"])
    problems = defaultdict(list)
    for index, (note, choice) in enumerate(zip(notes, choices)):
        position = (choice.get("string"), choice.get("fret"))
        if note["pitch"] is None:
            if position != (None, None):
                problems["null symbol given a position"].append(index + 1)
            continue
        if position not in {(p.string, p.fret) for p in candidate_positions(note["pitch"], setup)}:
            problems["no valid string + fret"].append(index + 1)
            continue
        finger = choice.get("finger")
        if finger is not None and (finger == 0) != (position[1] == 0):
            problems["finger 0 (open) only on fret 0, fingers 1–4 only on frets"].append(index + 1)
        if choice.get("stroke") not in (None, *STROKES):
            problems[f"stroke not one of {STROKES} or don't care"].append(index + 1)
    return [f"{reason}: notes {numbers}" for reason, numbers in problems.items()]


def add_way(reference_path: Path, source: dict[str, Any], passage: dict[str, Any], way: dict[str, Any],
            dry_run: bool = False) -> int:
    """Add one way to a passage's reference file, creating the file if needed; returns the way's number.

    Refuses (ValueError) a way with problems, a file holding another passage, and a way identical
    to one already in the file.

    Args:
        reference_path: The passage's reference file.
        source: Where the passage comes from (run source fields, without k_best).
        passage: The passage as a run file stores it.
        way: {"started_from": text, "comment": text or None, "choices": [...]}.
        dry_run: Check everything and return the number, but write nothing.
    """
    problems = way_problems(passage, way["choices"])
    if problems:
        raise ValueError("can't save yet — " + "; ".join(problems))
    snapshot = passage_snapshot(passage)
    if reference_path.exists():
        reference = json.loads(reference_path.read_text())
        if not same_passage(reference["passage"], snapshot):
            raise ValueError(f"{reference_path.name} holds a different passage ({reference['passage']['name']}); pick another name")
    else:
        reference = {"format": REFERENCE_FILE_FORMAT, "source": source, "passage": snapshot, "ways": []}

    # Only string, fret, finger, stroke are kept per note
    choices = [{field: choice.get(field) for field in ("passage_index", "string", "fret", "finger", "stroke")}
               for choice in way["choices"]]
    for number, existing in enumerate(reference["ways"], start=1):
        if existing["choices"] == choices:
            raise ValueError(f"identical to way {number} already in {reference_path.name}")
    if dry_run:
        return len(reference["ways"]) + 1

    reference["ways"].append({"saved": datetime.now().isoformat(timespec="seconds"),
                              "started_from": way["started_from"], "comment": way.get("comment"),
                              "choices": choices})
    reference_path.parent.mkdir(parents=True, exist_ok=True)
    reference_path.write_text(json.dumps(reference, indent=1, ensure_ascii=False))
    return len(reference["ways"])
