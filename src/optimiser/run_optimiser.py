"""Run the optimiser on a lick or a GP passage, print the realisations as tabs, optionally save as JSON.

Usage:
    uv run python -m src.optimiser.run_optimiser tests/optimiser/licks/a_minor_arpeggio.yaml
    uv run python -m src.optimiser.run_optimiser --gp song.gp5 --track 0 --bars 5-8
Options: --k (how many realisations), --tempo (override bpm), --tuning-shift (retune every string
by N semitones, pitches kept; e.g. -1 for a song in Eb saved as E standard), --voice, --breakdown (all moves),
--save (write the run as JSON to the run config's runs folder), --comment (added to the file name).

Tab rows: strings (1 = thinnest, on top), then stroke (D down, U up, h hammer-on, p pull-off,
s slide, t left-hand tap, H hammer-on from nowhere), finger (1–4 = index … pinky, 0 = open),
hand (fret where the index finger naturally sits). "*" = null symbol (chord / dead / unreachable).
"""

import argparse
import json
import re
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import yaml

from src.optimiser.cost_terms import NONE, TERM_HAND, load_cost_config
from src.optimiser.guitar_neck import load_guitar_setup
from src.optimiser.note_input import Passage, load_articulation_switches, load_gp_passage, load_lick
from src.optimiser.realisation_search import Realisation, search_realisations

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_CONFIG = REPO_ROOT / "configs/optimiser/optimiser_run_v0.1.yaml"
# Run-config fields that point at other config files (paths from the repo root)
CONFIG_POINTERS = ("guitar_setup", "cost_config", "gp_parser_config")
STROKE_LETTERS = {"down": "D", "up": "U"}
# Format tag + version written into every run file (the gp_viewer checks it)
RUN_FILE_FORMAT = {"name": "grip_optimiser_run", "version": "0.1"}


def load_run_config(run_config_path: Path) -> dict:
    """Read a run config, turning its pointers into absolute paths.

    Args:
        run_config_path: Path to a configs/optimiser/optimiser_run_v*.yaml file.
    """
    run_config = yaml.safe_load(Path(run_config_path).read_text())
    for pointer in CONFIG_POINTERS:
        run_config[pointer] = REPO_ROOT / run_config[pointer]
    return run_config


def stroke_letter(realisation: Realisation, index: int) -> str:
    """The stroke row's letter for one note.

    Args:
        realisation: The realisation (its passage gives the articulations).
        index: Index in realisation.passage.notes.
    """
    choice = realisation.choices[index]
    if choice.stroke != NONE:
        return STROKE_LETTERS[choice.stroke]
    articulations = realisation.passage.notes[index].articulations
    if "slide" in articulations:
        return "s"
    if "left_hand_tap" in articulations:
        return "t"
    move = next(move for move in realisation.moves if move.passage_index == index)
    if "hammer_on_from_nowhere" in move.terms:
        return "H"
    previous = next(c for c in reversed(realisation.choices[:index]) if c.position is not None)
    return "h" if choice.position.fret > previous.position.fret else "p"


def render_tab(realisation: Realisation) -> str:
    """ASCII tab with stroke, finger and hand rows.

    Args:
        realisation: The realisation.
    """
    string_count = realisation.passage.guitar.string_count
    rows = {name: [] for name in [*range(1, string_count + 1), "stroke", "finger", "hand"]}
    for index, choice in enumerate(realisation.choices):
        if choice.position is None:
            cells = {string: "*" for string in range(1, string_count + 1)}
            cells.update(stroke="*", finger="", hand="")
        else:
            cells = {string: "" for string in range(1, string_count + 1)}
            cells[choice.position.string] = str(choice.position.fret)
            cells.update(stroke=stroke_letter(realisation, index),
                         finger=str(choice.finger), hand=str(choice.hand))
        width = max(len(text) for text in cells.values()) + 1
        for name, text in cells.items():
            filler = "-" if isinstance(name, int) else " "
            rows[name].append(text.rjust(width, filler))
    lines = [f"{name}|{''.join(cells)}-" for name, cells in rows.items() if isinstance(name, int)]
    lines += [f"{name[0]} {''.join(cells)}" for name, cells in rows.items() if not isinstance(name, int)]
    return "\n".join(lines)


def render_breakdown(realisation: Realisation) -> str:
    """One line per move: picking case, every term, total and cost; then totals per hand.

    Args:
        realisation: The realisation.
    """
    term_names = list(TERM_HAND)
    header = f"{'note':>4} {'str':>3} {'fret':>4} {'case':<44}" + "".join(f"{n[:9]:>10}" for n in term_names)
    lines = [header + f"{'total':>8}{'cost':>8}"]
    hand_totals = {"fretting": 0.0, "picking": 0.0}
    for move in realisation.moves:
        choice = realisation.choices[move.passage_index]
        values = "".join(f"{move.terms.get(name, 0.0):>10.2f}" for name in term_names)
        case = move.picking_case or "-"
        lines.append(f"{move.passage_index + 1:>4} {choice.position.string:>3} {choice.position.fret:>4} "
                     f"{case:<44}{values}{move.total:>8.2f}{move.cost:>8.2f}")
        for name, value in move.terms.items():
            hand_totals[TERM_HAND[name]] += value
    lines.append(f"term sums by hand (before ** exponent): fretting {hand_totals['fretting']:.2f}, "
                 f"picking {hand_totals['picking']:.2f}")
    return "\n".join(lines)


def differing_notes(realisation: Realisation, best: Realisation) -> list[int]:
    """1-based note numbers where a realisation's tab differs from the best one.

    Args:
        realisation: An alternative.
        best: The cheapest realisation.
    """
    return [index + 1 for index, (a, b) in enumerate(zip(realisation.tab_key(), best.tab_key())) if a != b]


def passage_to_dict(passage: Passage) -> dict:
    """The passage as plain JSON-ready data: guitar, tempo, report and every note.

    Args:
        passage: The passage.
    """
    notes = []
    for index, note in enumerate(passage.notes):
        note_fields = asdict(note)
        note_fields["articulations"] = sorted(note.articulations)
        notes.append({"passage_index": index, **note_fields})
    return {"name": passage.name, "tempo_bpm": passage.tempo_bpm, "guitar": asdict(passage.guitar),
            "report": list(passage.report), "notes": notes}


def realisation_to_dict(realisation: Realisation, rank: int, best: Realisation) -> dict:
    """One realisation as plain JSON-ready data: choices (with stroke letters) and move costs.

    Args:
        realisation: The realisation.
        rank: 1 = cheapest.
        best: The cheapest realisation (for the differing notes).
    """
    choices = []
    for index, choice in enumerate(realisation.choices):
        playable = choice.position is not None
        choices.append({
            "passage_index": choice.passage_index,
            "string": choice.position.string if playable else None,
            "fret": choice.position.fret if playable else None,
            "finger": choice.finger, "hand": choice.hand, "stroke": choice.stroke,
            "stroke_letter": stroke_letter(realisation, index) if playable else None,
        })
    return {"rank": rank, "total_cost": realisation.total_cost,
            "differs_at_notes": differing_notes(realisation, best),
            "choices": choices, "moves": [asdict(move) for move in realisation.moves]}


def build_run_record(realisations: list[Realisation], source: dict, comment: str | None,
                     search_seconds: float, run_config: dict, run_config_path: Path = RUN_CONFIG) -> dict:
    """Everything one run produced and used, standalone: passage, settings snapshot, realisations.

    Args:
        realisations: Search results, cheapest first (all share one passage).
        source: Where the passage came from (lick file, or GP file + track / bars / voice) and overrides.
        comment: Free text from --comment, or None.
        search_seconds: Search time.
        run_config: The loaded run config (pointers already absolute).
        run_config_path: The run config file, snapshotted as read.
    """
    # Settings snapshot: the config files exactly as read, so the run stays comparable after edits
    settings = {"run_config": yaml.safe_load(Path(run_config_path).read_text())}
    for pointer in CONFIG_POINTERS:
        settings[pointer] = yaml.safe_load(Path(run_config[pointer]).read_text())
    best = realisations[0]
    return {
        "format": RUN_FILE_FORMAT, "created": datetime.now().isoformat(timespec="seconds"),
        "comment": comment, "source": source, "search_seconds": round(search_seconds, 3),
        "term_hand": TERM_HAND, "settings": settings,
        "passage": passage_to_dict(best.passage),
        "realisations": [realisation_to_dict(realisation, rank, best)
                         for rank, realisation in enumerate(realisations, start=1)],
    }


def free_run_path(runs_folder: Path, passage_name: str, comment: str | None) -> Path:
    """yymmdd_<passage>[_<comment>].json in the runs folder; _2, _3 … appended if the name is taken.

    Args:
        runs_folder: Folder holding run files.
        passage_name: Passage name (turned into lowercase words joined by _).
        comment: Optional free text from --comment.
    """
    parts = [datetime.now().strftime("%y%m%d"), passage_name] + ([comment] if comment else [])
    stem = "_".join(re.sub(r"[^a-z0-9]+", "_", part.lower()).strip("_") for part in parts)
    path, copy_number = runs_folder / f"{stem}.json", 2
    while path.exists():
        path, copy_number = runs_folder / f"{stem}_{copy_number}.json", copy_number + 1
    return path


def load_source_passage(source: dict, run_config_path: Path = RUN_CONFIG) -> Passage:
    """Load the passage a run source names, with the run config's guitar and articulation switches.

    Args:
        source: {"lick": path} or {"gp": path, "track", "bars" ("5-8", 1-based inclusive), "voice"},
            plus "tempo_override_bpm" (None = the file's) and "tuning_shift" (semitones).
        run_config_path: The run config to read.
    """
    run_config = load_run_config(run_config_path)
    guitar = load_guitar_setup(run_config["guitar_setup"])
    switches = load_articulation_switches(run_config_path)
    tempo, tuning_shift = source.get("tempo_override_bpm"), source.get("tuning_shift", 0)
    if "gp" in source:
        first_bar, last_bar = (int(bar) for bar in source["bars"].split("-"))
        return load_gp_passage(Path(source["gp"]), source["track"], first_bar, last_bar, guitar, switches,
                               run_config["gp_parser_config"], source["voice"], tempo, tuning_shift)
    return load_lick(Path(source["lick"]), guitar, switches, tempo, tuning_shift)


def run_search(source: dict, k_best: int | None, comment: str | None,
               run_config_path: Path = RUN_CONFIG) -> tuple[list[Realisation], dict]:
    """Load the source's passage, search it, and build the run record (see build_run_record).

    Args:
        source: See load_source_passage; the record's copy gets "k_best" added.
        k_best: How many realisations; None = the run config's k_best.
        comment: Free text kept in the record, or None.
        run_config_path: The run config to read.

    Returns:
        The realisations (cheapest first) and the run record.
    """
    run_config = load_run_config(run_config_path)
    search = run_config["search"]
    passage = load_source_passage(source, run_config_path)
    k_best = k_best or search["k_best"]
    started = time.perf_counter()
    realisations = search_realisations(passage, load_cost_config(run_config["cost_config"]), k_best,
                                       search["k_search_multiplier"], search["pick_memory_notes"])
    seconds = time.perf_counter() - started
    record = build_run_record(realisations, {**source, "k_best": k_best}, comment, seconds, run_config,
                              run_config_path)
    return realisations, record


def save_run_record(record: dict, run_config_path: Path = RUN_CONFIG) -> Path:
    """Write a run record to the run config's runs folder under a free name; returns the path.

    Args:
        record: Output of build_run_record.
        run_config_path: The run config naming the runs folder.
    """
    runs_folder = REPO_ROOT / load_run_config(run_config_path)["output"]["runs_folder"]
    run_path = free_run_path(runs_folder, record["passage"]["name"], record["comment"])
    run_path.write_text(json.dumps(record, indent=1, ensure_ascii=False))
    return run_path


def main() -> None:
    """Parse arguments, load the passage, search, print."""
    parser = argparse.ArgumentParser(description="GRIP optimiser (Layer 1): cheapest realisations of a passage")
    parser.add_argument("lick", nargs="?", help="hand-typed lick file (YAML)")
    parser.add_argument("--gp", help="GP file instead of a lick")
    parser.add_argument("--track", type=int, default=0, help="GP track, from 0")
    parser.add_argument("--bars", default="1-4", help="GP bar range, 1-based inclusive, e.g. 5-8")
    parser.add_argument("--voice", type=int, default=0, help="GP voice, from 0")
    parser.add_argument("--tempo", type=float, help="override the tempo (bpm)")
    parser.add_argument("--tuning-shift", type=int, default=0,
                        help="retune every string by N semitones, pitches kept (e.g. -1: Eb saved as E standard)")
    parser.add_argument("--k", type=int, help="how many realisations (default: run config)")
    parser.add_argument("--breakdown", action="store_true", help="print every move of every realisation")
    parser.add_argument("--save", action="store_true", help="write the run as JSON to the runs folder")
    parser.add_argument("--comment", help="free text added to the run file's name and contents (with --save)")
    args = parser.parse_args()

    if args.gp:
        source = {"gp": args.gp, "track": args.track, "bars": args.bars, "voice": args.voice}
    elif args.lick:
        source = {"lick": args.lick}
    else:
        parser.error("give a lick file or --gp")
    source.update(tempo_override_bpm=args.tempo, tuning_shift=args.tuning_shift)

    realisations, record = run_search(source, args.k, args.comment)
    passage, seconds = realisations[0].passage, record["search_seconds"]

    print(f"== {passage.name} — {passage.tempo_bpm:g} bpm, {sum(not n.is_null for n in passage.notes)} notes, "
          f"tuning {passage.guitar.tuning}, searched in {seconds:.1f} s")
    for line in passage.report:
        print(f"   report: {line}")
    best = realisations[0]
    for rank, realisation in enumerate(realisations, start=1):
        differs = "" if rank == 1 else f" — differs at notes {differing_notes(realisation, best)}"
        print(f"\n#{rank}  cost {realisation.total_cost:.2f}{differs}")
        print(render_tab(realisation))
        if rank == 1 or args.breakdown:
            print(render_breakdown(realisation))

    # Save the whole run as one standalone JSON file (opt-in)
    if args.save:
        run_path = save_run_record(record)
        print(f"\nsaved: {run_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
