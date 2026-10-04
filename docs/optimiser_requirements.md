# Optimiser requirements

What GRIP's own fretting-hand optimiser must do. The optimiser takes a note sequence and generates
a set of playable realisations (string + fret per note, possibly finger / hand position).

- Origin: R1–R12 from the optimiser survey brief (`docs/survey/optimisers/brief.md`, 2026-10-03),
  revised with Jae on 2026-10-04 after the survey walkthrough.
- Mirror: Notion hub → Optimiser → Requirements. Keep both in sync; Notion wins on plan.

## Requirements

| id | requirement |
|---|---|
| R1 | **Input:** monophonic note sequence, pitch + onset + duration per note |
| R2 | **Instrument setup as input:** per-string tuning (incl. drop tunings), 6 or 7 strings. Capo not required for now |
| R3 | **Several realisations:** returns a set, not one fingering |
| R4 | **Meaningful alternatives:** an alternative counts by its *effect* (lower difficulty and/or a different technique profile, including the effect on following notes), not by how many notes changed. One-note changes count |
| R5 | **Technique-agnostic generation:** no technique labels, pick-direction plans or compatibility scores in the generation cost. User technique preferences re-rank the frozen set; they never steer generation |
| R6 | **Decomposable cost:** per-term, per-transition breakdown, reusable by the difficulty readout |
| R7 | **Hard vs soft, nothing impossible by assumption:** hard feasibility kept separate from soft playability cost. Every "impossible" rule or threshold needs Jae's approval; very hard = expensive, never deleted |
| R8 | **Physical geometry:** stretch measured in mm (frets narrow up the neck), not fret count. Scale length is a setting |
| R9 | **Timing-aware:** a shift costs more when there is less time to make it |
| R10 | **Fretting-hand state:** models hand position and/or finger assignment |
| R11 | **Optimality over speed:** CPU, thousands of phrases; spend compute on a richer model rather than instant response |
| R12 | **Licence:** reuse code only under MIT / BSD / Apache-style licences; GPL or unlicensed code = ideas and cost terms only (public repo) |

## Details

### R1: input
- Scope: leads, solos, melodies, single-note riffs. Chords, strumming and rhythm parts are out.
- Onset and duration are needed for R9 (timing) and for phrase design.

### R2: instrument setup
- Setup is a whole-song choice, not part of the fingering.
- Drop tuning changes the low-string note ladder; the generator searches that neck.
- Capo: dropped as a requirement on 2026-10-04. GP capo conventions stay an open parser question.

### R3 + R4: the realisation set
- Plain k-best (2nd, 3rd … cheapest) returns hundreds of 1–5-note tweaks (survey: 4 tools).
  Under R4 these are raw material, not failures.
- Core job: filter many small tweaks down to the few whose effect matters.
- "Effect" = lowers the difficulty readout and/or changes the technique profile, judged over the
  passage and the notes that follow, not the local move alone.
- Exact cost ties are where the cost cannot decide → technique / preference re-ranking decides.
- Open: the threshold for "meaningful".
- Candidate mechanisms (survey, provisional): per-note view + lock-and-resolve, forced detours
  (via-node), penalised reruns (diverse M-best), pick-a-spread selection measured on readouts.

### R5: technique-agnostic generation
- Invariant: generate → freeze → analyse techniques.
- Decided 2026-10-04: preferences re-rank a fixed set; steering generation risks forcing
  unrealistic fingerings.
- Jae's concern to keep in view: a technique-blind generator might hand over only a route that
  needs an unpleasant technique (e.g. frequent tapping) while missing a route that allows sweep
  picking or a string skip. The set must be rich enough for re-ranking to find the good one.
- Open: is a string-change cost fretting-hand playability or picking-hand technique?
  (Heijink 2002: string-change demand is absorbed by the time between notes.)
- Technique families alternate / economy / legato are provisional; the target is finer and useful
  to intermediate + advanced players (e.g. economy picking split by direction).

### R6: decomposable cost
- Each term (shift, stretch, height, …) logged separately per note pair, so the difficulty
  readout can reuse the same ergonomic profile.

### R7: hard vs soft
- Difficult pieces often *feel* impossible without being impossible.
- Any hard limit found in the literature (e.g. 4-fret hand window, 5-fret span) is an assumption
  awaiting Jae's sign-off, not a default.
- Never drop or octave-shift a note silently; report infeasible input explicitly.

### R8: physical geometry
- Equal-temperament fret positions: distance from nut to fret n = L · (1 − 2^(−n/12)),
  L = scale length.
- Example (L = 648 mm): 3 frets span ≈ 97 mm near the nut vs ≈ 52 mm at fret 12.
- Open: default guitar / scale length (proposed 648 mm, as a setting).
- Novelty note: mm distances alone are not new (piano tools, Rodríguez & Klapuri, Heijink);
  combining mm with string/fret choice and timing is what the survey didn't find.

### R9: timing
- Current idea: shift cost scaled by the time available (Hori family: distance ÷ time).
- Survey test phrase 3: five time-blind tools kept a slow line at frets 7–17 to avoid one shift,
  despite a 2 s held note.
- Detailed design deferred to the optimiser build session.

### R10: fretting-hand state
- Options: (string, fret, finger) with hand anchor = fret − finger + 1, or (string, fret,
  hand position) with a hand window. Choice open.

### R11: optimality over speed
- The standard search is already exact over a whole phrase and takes milliseconds.
- Extra compute buys a richer model (more in each state, wider cost window, longer phrases),
  not more look-ahead.
- Student tool option: re-finger the notes after a highlighted passage too.

### R12: licence
- Survey licence status per tool: `docs/survey/optimisers/report.md` (local).

## Design questions (not requirements)
- **Phrase / cluster definition** = core research question; designed and tested hands-on.
  - Direction: a musical unit (lick, bar), often 8/12/16/24 notes, bounded by where the hand
    has to shift far. Not a fixed number of notes ahead.
  - Open: one hand position per phrase vs up to two.
  - Chicken-and-egg: phrase cuts depend on shifts, shifts depend on cuts → choose both in one search?
  - Free starting cut points: bar lines, rests, note groupings in the GP file.
  - Soft hint (not a rule): a passage starting on an upstroke usually still belongs to the
    ongoing phrase → borders may prefer a downstroke start. Uses pick direction → check against R5.
- **Cost terms:** case-by-case review by Jae (e.g. "pinky is expensive" is too blunt), not
  literature defaults.
- **Known traps** (survey): open-string free jumps, drift to high frets, silent note drops,
  silent hard limits, rewriting the fingering after solving.
