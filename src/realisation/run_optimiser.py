"""Run the optimiser on a lick or a GP passage and print the realisations as tabs.

Usage:
    uv run python -m src.realisation.run_optimiser tests/realisation/licks/a_minor_arpeggio.yaml
    uv run python -m src.realisation.run_optimiser --gp song.gp5 --track 0 --bars 5-8
Options: --k (how many realisations), --tempo (override bpm), --voice, --breakdown (all moves).

Tab rows: strings (1 = thinnest, on top), then stroke (D down, U up, h hammer-on, p pull-off,
s slide, t left-hand tap, H hammer-on from nowhere), finger (1–4 = index … pinky, 0 = open),
hand (fret where the index finger naturally sits). "*" = null symbol (chord / dead / unreachable).
"""

import argparse
import time
from pathlib import Path

import yaml

from src.realisation.cost_terms import NONE, TERM_HAND, load_cost_config
from src.realisation.guitar_neck import load_guitar_setup
from src.realisation.note_input import Passage, load_articulation_switches, load_gp_passage, load_lick
from src.realisation.realisation_search import Realisation, search_realisations

REPO_ROOT = Path(__file__).resolve().parents[2]
COST_CONFIG = REPO_ROOT / "configs/realisation/optimiser_cost_v0.1.yaml"
RUN_CONFIG = REPO_ROOT / "configs/realisation/optimiser_run_v0.1.yaml"
STROKE_LETTERS = {"down": "D", "up": "U"}


def stroke_letter(realisation: Realisation, passage: Passage, index: int) -> str:
    """The stroke row's letter for one note.

    Args:
        realisation: The realisation.
        passage: The passage (articulations).
        index: Index in passage.notes.
    """
    choice = realisation.choices[index]
    if choice.stroke != NONE:
        return STROKE_LETTERS[choice.stroke]
    articulations = passage.notes[index].articulations
    if "slide" in articulations:
        return "s"
    if "left_hand_tap" in articulations:
        return "t"
    move = next(move for move in realisation.moves if move.passage_index == index)
    if "hammer_on_from_nowhere" in move.terms:
        return "H"
    previous = next(c for c in reversed(realisation.choices[:index]) if c.position is not None)
    return "h" if choice.position.fret > previous.position.fret else "p"


def render_tab(realisation: Realisation, passage: Passage) -> str:
    """ASCII tab with stroke, finger and hand rows.

    Args:
        realisation: The realisation.
        passage: The passage.
    """
    string_count = passage.guitar.string_count
    rows = {name: [] for name in [*range(1, string_count + 1), "stroke", "finger", "hand"]}
    for index, choice in enumerate(realisation.choices):
        if choice.position is None:
            cells = {string: "*" for string in range(1, string_count + 1)}
            cells.update(stroke="*", finger="", hand="")
        else:
            cells = {string: "" for string in range(1, string_count + 1)}
            cells[choice.position.string] = str(choice.position.fret)
            cells.update(stroke=stroke_letter(realisation, passage, index),
                         finger=str(choice.finger), hand=str(choice.hand))
        width = max(len(text) for text in cells.values()) + 1
        for name, text in cells.items():
            filler = "-" if isinstance(name, int) else " "
            rows[name].append(text.rjust(width, filler))
    lines = [f"{name}|{''.join(cells)}-" for name, cells in rows.items() if isinstance(name, int)]
    lines += [f"{name[0]} {''.join(cells)}" for name, cells in rows.items() if not isinstance(name, int)]
    return "\n".join(lines)


def render_breakdown(realisation: Realisation, passage: Passage) -> str:
    """One line per move: picking case, every term, total and cost; then totals per hand.

    Args:
        realisation: The realisation.
        passage: The passage.
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


def main() -> None:
    """Parse arguments, load the passage, search, print."""
    parser = argparse.ArgumentParser(description="GRIP optimiser (Layer 1): cheapest realisations of a passage")
    parser.add_argument("lick", nargs="?", help="hand-typed lick file (YAML)")
    parser.add_argument("--gp", help="GP file instead of a lick")
    parser.add_argument("--track", type=int, default=0, help="GP track, from 0")
    parser.add_argument("--bars", default="1-4", help="GP bar range, 1-based inclusive, e.g. 5-8")
    parser.add_argument("--voice", type=int, default=0, help="GP voice, from 0")
    parser.add_argument("--tempo", type=float, help="override the tempo (bpm)")
    parser.add_argument("--k", type=int, help="how many realisations (default: run config)")
    parser.add_argument("--breakdown", action="store_true", help="print every move of every realisation")
    args = parser.parse_args()

    run_config = yaml.safe_load(RUN_CONFIG.read_text())["search"]
    guitar = load_guitar_setup(RUN_CONFIG)
    switches = load_articulation_switches(RUN_CONFIG)
    cost_config = load_cost_config(COST_CONFIG)
    if args.gp:
        first_bar, last_bar = (int(bar) for bar in args.bars.split("-"))
        passage = load_gp_passage(Path(args.gp), args.track, first_bar, last_bar, guitar, switches,
                                  args.voice, args.tempo)
    elif args.lick:
        passage = load_lick(Path(args.lick), guitar, switches, args.tempo)
    else:
        parser.error("give a lick file or --gp")

    started = time.perf_counter()
    realisations = search_realisations(passage, cost_config, args.k or run_config["k_best"],
                                       run_config["k_search_multiplier"], run_config["pick_memory_notes"])
    seconds = time.perf_counter() - started

    print(f"== {passage.name} — {passage.tempo_bpm:g} bpm, {sum(not n.is_null for n in passage.notes)} notes, "
          f"tuning {passage.guitar.tuning}, searched in {seconds:.1f} s")
    for line in passage.report:
        print(f"   report: {line}")
    best = realisations[0]
    for rank, realisation in enumerate(realisations, start=1):
        differs = "" if rank == 1 else f" — differs at notes {differing_notes(realisation, best)}"
        print(f"\n#{rank}  cost {realisation.total_cost:.2f}{differs}")
        print(render_tab(realisation, passage))
        if rank == 1 or args.breakdown:
            print(render_breakdown(realisation, passage))


if __name__ == "__main__":
    main()
