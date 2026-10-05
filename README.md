# guitar-realisation-inference-and-profiling (GRIP)

Given pitch + timing only, generate several highly playable realisations (fingering + pick
plan, priced by both the fretting hand and the picking hand) and recover missing
physical-performance information: where the notes can plausibly be played, and which
techniques those realisations support.

Project facts → [PROJECT.md](PROJECT.md).

## How to use

### Optimiser: cheapest realisations of a passage
```bash
# A hand-typed lick (top 3 realisations)
uv run python -m src.realisation.run_optimiser tests/realisation/licks/a_minor_arpeggio.yaml --k 3

# A passage from a GP file: track 0, bars 1–2 (bars as Guitar Pro numbers them)
uv run python -m src.realisation.run_optimiser \
  --gp "$HOME/storage/grip/datasets/dadagp/DadaGP-v1.1/S/Stratovarius/Stratovarius - Stratosphere (2).gp3" \
  --track 0 --bars 1-2 --k 3
```
- Options: `--tempo 140` overrides the bpm · `--voice 1` picks another GP voice ·
  `--breakdown` prints the cost of every move for every realisation (default: the best only).
- Output rows: strings (1 = thinnest, on top), then `s` stroke (`D` down, `U` up, `h` / `p`
  hammer-on / pull-off, `s` slide, `t` left-hand tap, `H` hammer-on from nowhere), `f` finger
  (1–4 = index … pinky, 0 = open), `h` hand position (fret under the index finger).
  `*` = null symbol (chord, dead note, or a note this guitar can't reach).
- Knobs: `configs/realisation/optimiser_cost_v0.1.yaml` (costs) and
  `configs/realisation/optimiser_run_v0.1.yaml` (guitar, k, articulation switches).
- Lick files: `tests/realisation/licks/*.yaml`. Each note is `[pitch, beats]` or
  `[pitch, beats, [articulations]]`; pitch = a note name (`A3`, `C#4`), `rest`, `x` (dead note) or
  a list (chord); beats in quarter notes (`0.25` = a 16th); articulations: `bend`, `legato`,
  `slide`, `left_hand_tap`.

### GP viewer: see and hear a GP file in the browser
```bash
uv run python -m src.gp_viewer.server
```
Open <http://localhost:8765> (VS Code Remote-SSH forwards the port from sym8). Search the track
list (e.g. `stratosphere`) or paste a path under the DadaGP root into the path box, e.g.
`S/Stratovarius/Stratovarius - Stratosphere (2).gp3`.
