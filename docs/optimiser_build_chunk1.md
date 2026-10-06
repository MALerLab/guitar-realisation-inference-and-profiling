# Optimiser build — chunk 1 spec (Layer 1, pick only)

What chunk 1 builds, distilled from `docs/optimiser_design_log.md` (topics 1–8). The log holds
the reasons; `configs/optimiser/optimiser_cost_v0.1.yaml` holds every number. Conflict →
requirements doc > design log > this spec.

**Goal:** a hand-typed lick (or a passage cut from a GP file) → the single cheapest two-hand
realisation (string, fret, finger, hand position, stroke per note), printed as a tab with a
per-term cost breakdown, so Jae can judge it guitar in hand.

## In scope
- **Input** (topic 1): notes = MIDI pitch, onset + duration in seconds (ticks kept); tempo; instrument setup. Chords / double-stops / dead notes → a null symbol with the
  same onset + duration: no cost, both hands carry their state across.
- **Enforced articulations** (topic 5; all on by default): bend → fretted note (open string =
  `open_string_bend` cost); hammer-on / pull-off, slide, left-hand tap → stroke = none (slide also
  same string as the previous note).
- **Instrument** (topic 2): per-string tuning, 6 or 7 strings, highest fret (24), scale length
  (648 mm). Fret n at L · (1 − 2^(−n/12)) mm.
- **Candidates** (topic 2): every (string, fret) that sounds the pitch, open strings included,
  no pruning. A note no string reaches → reported, never dropped.
- **State per note** (topics 3–5): position (string, fret) · finger (1–4, or none for an open
  string) · hand position (where the index finger naturally sits) · stroke (down / up / none) ·
  pick memory (string + direction of the last *picked* note, and how many notes back it was).
- **Search** (topic 3): exact column-by-column search (Viterbi) over the whole input passage;
  costs compare this state with the previous one only.
- **Cost terms** (topics 6–8), each with its own knob, tagged by hand:
  - picking table case × (reference gap ÷ time since the last picked note)
  - legato × (reference gap ÷ time since the previous note)
  - hammer-on from nowhere, open-string bend: flat
  - shift: steep up to a knee (≈ 3 frets, mm), gentle linear after, × (reference gap ÷ time)
  - stretch: finger distance from its natural spot under the hand, mm, every note
  - adding up: each transition's total ** `big_move_exponent`, then summed
- **Hard rule #1:** a new phrase starts with a downstroke (no upstroke). Phrase start = first note,
  or after a rest ≥ `rest_min_beats` (bar lines: toggle, off).
- **k-best** (Jae, 2026-10-05): the k cheapest realisations (plain k-best; expect 1–5-note
  tweaks = raw material for R6). The "meaningful" filter stays out.
- **Starting tempo** (parser to-do #1, folded into step 2): read from the GP file; manual
  override for hand-typed licks.
- **Output:** realisation + cost breakdown per transition, per term, per hand (R10); ASCII tab.

## Out of scope (chunk 1) → intention vs limitation recorded at the end of the build
- Hybrid picking + right-hand tapping → chunk 2 (scheduled).
- The "meaningful" filter (R6) → later chunk.
- Layer 2 (chunk level, phrase finding) → after the Layer 1 experiment.
- Streak / endurance effects, silent strokes through short rests, finger rolls, vibrato, let ring.
- Bends switched off, tempo changes (parser to-dos #2, #3).

## Build steps — Claude stops after each one and shows Jae
1. Instrument setup, fret geometry, candidates
2. Note input: hand-typed licks + from GP (incl. starting tempo), null symbols, enforced articulations
3. State space + cost terms (each term testable on a single transition)
4. Search + k-best + cost breakdown
5. Output: ASCII tab with strokes + breakdown table; one run command
6. First licks → Jae judges guitar in hand → first knob tuning

## Files
| file | holds |
|---|---|
| `src/optimiser/guitar_neck.py` | guitar setup (tuning, strings, highest fret, scale length), fret positions in mm, candidate positions per note |
| `src/optimiser/note_input.py` | input contract: notes, null symbols, enforced articulations, starting tempo; from hand-typed licks or GP |
| `src/optimiser/cost_terms.py` | one named function per cost term + breakdown |
| `src/optimiser/realisation_search.py` | state space + exact search + k-best |
| `src/optimiser/run_optimiser.py` | `uv run python -m src.optimiser.run_optimiser <lick>`; ASCII tab + breakdown printout |
| `configs/optimiser/optimiser_cost_v0.1.yaml` | all cost knobs (exists; shift / stretch values filled in) |
| `configs/optimiser/optimiser_run_v0.1.yaml` | the whole run: k, articulation switches, pointers to the guitar setup, cost knobs and GP parser config |
| `configs/optimiser/guitar_setup/default.yaml` | default guitar (standard tuning, 6 strings, 24 frets, 648 mm); a GP file's or lick's tuning replaces its tuning |
| `tests/optimiser/licks/*.yaml` | generic hand-typed test licks (tracked; no song excerpts) |
| `tests/optimiser/test_*.py` | behaviour tests, one file per source file |

Song excerpts (benchmark songs) are cut from local GP files at run time and never committed
(public repo).

## Testing
- Behaviour tests, not re-implementations, e.g.: E4 has 6 candidates on a 24-fret standard
  guitar; fret 12 sits at 324 mm; an enforced hammer-on gets stroke = none; a null symbol costs
  nothing and keeps both hands' state; a phrase never starts with an upstroke; a down-down sweep
  costs less than a down → up crossing on the same transition.
- The real test is Jae with a guitar: does the printed tab look like what a guitarist would do?
  First licks: the A minor arpeggio (requirements doc, R2), a 3-notes-per-string run, a slow line
  with a long held note (survey test phrase 3), a *Stratosphere* excerpt from a local GP file.
- Speed: measure states per note and run time on the longest test lick.
