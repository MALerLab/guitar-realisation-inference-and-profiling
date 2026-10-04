# Optimiser requirements

What GRIP's own two-hand optimiser must do. The optimiser takes a note sequence and generates
a set of playable realisations (string + fret + pick direction per note, possibly finger / hand
position), priced by the effort of both the fretting hand and the picking hand.

- Origin: R1–R12 from the optimiser survey brief (`docs/survey/optimisers/brief.md`, 2026-10-03),
  revised with Jae on 2026-10-04 after the survey walkthrough.
- Rewrite 2026-10-04: picking-hand model added; "technique-agnostic generation" replaced by
  "no technique favouritism"; requirements reordered by importance.
  - Old → new ids: R1→R1 · R2→R11 · R3→R5 · R4→R6 · R5→R7 · R6→R10 · R7→R8 · R8→R9 ·
    R9→R4 · R10→R3 · R11→R12 · R12→R13 · R2 is new. The survey files use the old ids.
- Mirror: Notion hub → Optimiser → Requirements. Keep both in sync; Assume repo version is up-to-date.

## Requirements

| id | requirement |
|---|---|
| R1 | **Input:** monophonic note sequence, pitch + onset + duration per note. Nothing else from the source tab enters generation: no fingering, technique marks or pickstroke marks |
| R2 | **Picking-hand model, equal weight:** the cost models the picking hand with the same importance as the fretting hand; this is the project's core. A realisation = fingering + pick plan, chosen together in one search, because each hand's best choice depends on the other. Tracks the last stroke direction, so string crossings, string skips and sweeps are priced. Default: the player is equally proficient in every picking technique. Hammer-ons / pull-offs count where they change playability (a note that can't be picked in time); otherwise they're style. How to tell the two apart is decided at the picking-hand build step |
| R3 | **Fretting-hand state:** tracks both the fingers and the hand (wrist), for different things |
| R4 | **Timing-aware:** a hand movement (fretting-hand shift, picking-hand string crossing) costs more when there is less time to make it. This involves note-density + tempo |
| R5 | **Several realisations:** returns a set, not one fingering |
| R6 | **Meaningful alternatives:** an alternative counts by its *effect* (lower difficulty and/or a different technique profile, including the effect on following notes), not by how many notes changed. One-note changes count if they produce a meaningful difference in how the difficulty changes, future notes change, or different techniques become in/compatible |
| R7 | **No technique favouritism:** generation never drops or ranks down a realisation for suiting one technique badly; it's still playable, on a different avenue. Technique compatibility (e.g. economy 24 %, alternate 98 %) is computed after generation. A technique is favoured only once the user states a preference, and preferences re-rank the generated set |
| R8 | **Hard vs soft, nothing impossible by assumption:** hard feasibility kept separate from soft playability cost. Every "impossible" rule or threshold needs Jae's approval; very hard = expensive, never deleted |
| R9 | **Physical geometry:** stretch measured in mm (frets narrow up the neck), not fret count. Scale length pending decision |
| R10 | **Decomposable cost:** per-term, per-transition breakdown, split by hand, reusable by the difficulty readout |
| R11 | **Instrument setup as input:** per-string tuning (incl. drop tunings), 6 or 7 strings. Capo not required for now |
| R12 | **Optimality over speed:** CPU, thousands of phrases; spend compute on a richer model rather than instant response |
| R13 | **Licence:** reuse code only under MIT / BSD / Apache-style licences; GPL or unlicensed code = ideas and cost terms only (public repo) |

## Details

### R1: input
- Scope: leads, solos, melodies, single-note riffs. Chords, strumming and rhythm parts are out.
- Onset and duration feed R4 (timing-aware) and phrase design.
- The source tab is evidence for pitch + timing only. Its fingering, technique marks and
  pickstroke marks stay hidden from generation, because the evaluation checks whether the
  pipeline recovers them.

### R2: picking-hand model
- The project's core: the picking hand gets the same weight as the fretting hand.
  - Survey (2026-10-03): no surveyed tool that chooses string + fret tracks pick direction. Some
    charge a flat string-change cost without it (Hori & Sagayama 2016, Bontempi, `gtrsnipe`).
  - Picking-hand effort appears only as difficulty features on a fixed tab (Rodríguez & Klapuri
    2025, Müllerschön et al. 2025, Vélez Vásquez et al. 2023).
- Chicken-and-egg: the fretting hand's best fret depends on the pick plan, and the pick plan
  mostly follows from the fingering → one search over both hands. Each search step holds the
  fretting-hand state (R3) plus the last stroke direction.
- Default: the player is equally proficient in every picking technique. Under it, the pick plan
  is mostly determined by the fingering (the most ergonomic plan), with some room for variants.
  - The same fingering with a different pick plan can be its own alternative (R6).
- Example, A minor arpeggio A3 C4 E4 A4 C5:
  - sweep shape 12-10-9-10-8 on strings A D G B e: one note per string, 4 string crossings.
    All downstrokes → the crossings are nearly free; strict down-up → every crossing is awkward.
  - 2-notes-per-string version (A 12, A 15, D 14, G 14, G 17): 2 crossings.
  - A string-change cost without stroke direction ranks the sweep shape down.
- For the fretting hand alone, a string change is nearly free: the finger lands early, because
  the new string isn't sounding yet (Heijink & Meulenbroek 2002). The string-change cost sits
  mainly in the picking hand.
- Legato (Jae's test): if leaving a hammer-on / pull-off out doesn't hurt playability, it's style;
  if a note can't be picked in time, it's playability.
  - Probably: pick plan per note = down, up, or none (hammer-on / pull-off).
- Open (build step): what the picking-hand state holds besides the last stroke direction.

### R3: fretting-hand state
- Fingers and hand are tracked for different things:
  - fingers: stretch, finger order, feasibility
  - hand (wrist): shifts
- Example: the same 6-fret move is nearly free from index (fret 12) to pinky (fret 18), because
  the fingers spread and the hand stays. From pinky (fret 12) to index (fret 18) it's costly,
  because the whole hand slides about 9 frets.
- Hand position idea (Jae): hand centre ≈ the average of recent finger positions, e.g. between
  middle and ring finger, whether or not they're playing. Full design at the build step.
- Trap: the textbook formula "hand position = fret − finger + 1" (Itoh, Hori, Bontempi) assumes
  one finger per fret, so it reads a stretch as a shift: index 12 → pinky 18 gives a 3-fret
  "shift" that never happened. "Hand = lowest fretted fret" has the same flaw (survey: TabSampler).
- Open strings need no finger; the hand stays where it was (fixes the survey's "free teleport"
  trap).
- Memo (Jae): a same-fret move to the neighbouring string (e.g. fret 8 → fret 8 one string over)
  often sounds muddy and is hard to play clean. Candidate cost term; it also covers finger rolls
  (one finger across two strings at the same fret, common in sweep shapes).

### R4: timing-aware
- Current idea: movement cost scaled by the time available (Hori family: distance ÷ time).
- Both hands: a string crossing with too little time is what makes a hammer-on / pull-off
  necessary (R2).
- Speed needs tempo: ticks give note values (16ths vs quarters), not how fast a beat is.
  - The GP parser outputs ticks (960 per quarter note) and doesn't read bpm yet
    (`docs/parser_audit.md`, decision 12, timing unit). Reading tempo changes is deferred.
  - Only the time between neighbouring notes is needed, so repeats can stay unplayed-out
    (exception: the jump at a repeat sign).
- Survey test phrase 3: five time-blind tools kept a slow line at frets 7–17 to avoid one shift,
  despite a 2 s held note.
- Detailed design at the build step.

### R5 + R6: the realisation set
- Plain k-best (2nd, 3rd … cheapest) returns hundreds of 1–5-note tweaks (survey: 4 tools).
  Under R6 these are raw material, not failures.
- Core job: filter many small tweaks down to the few whose effect matters.
- "Effect" = lowers the difficulty readout and/or changes the technique profile, judged over the
  passage and the notes that follow, not the local move alone.
- Exact cost ties are where the cost cannot decide; user preferences may decide later (next
  stage, R7).
- Open: the threshold for "meaningful".
- Candidate mechanisms (survey, provisional): per-note view + lock-and-resolve, forced detours
  (via-node), penalised reruns (diverse M-best), pick-a-spread selection measured on readouts.

### R7: no technique favouritism
- Replaces "technique-agnostic generation" (2026-10-04). The intent was always "don't drop a
  realisation for suiting one technique badly". The old name drifted into "keep the picking hand
  out of generation", which contradicts R2 (picking-hand model).
- Still forbidden in generation: dropping or ranking down a realisation for suiting one technique
  badly; using the source tab's fingering or technique marks (R1).
- Allowed in generation: picking-hand effort, pick direction, legato where it changes
  playability (R2).
- Compatibility doesn't always need computing from scratch: if generation keeps its reasoning
  (pick plan, cost breakdown), the technique readout may reuse it.
- User preferences (per technique, per mode: drill vs learn easily) = next stage of the project.
  The working optimiser comes first, everything downstream second.
  - Decided so far: preferences re-rank the generated set; they never steer generation.
- Technique families alternate / economy / legato are provisional; the target is finer and useful
  to intermediate + advanced players (e.g. economy picking split by direction).

### R8: hard vs soft
- Applies to both hands.
- Difficult pieces often *feel* impossible without being impossible.
- Any hard limit found in the literature (e.g. 4-fret hand window, 5-fret span) is an assumption
  awaiting Jae's sign-off, not a default.
- Never drop or octave-shift a note silently; report infeasible input explicitly.

### R9: physical geometry
- Equal-temperament fret positions: distance from nut to fret n = L · (1 − 2^(−n/12)),
  L = scale length.
- Example (L = 648 mm): 3 frets span ≈ 97 mm near the nut vs ≈ 52 mm at fret 12.
- Open: scale length (648 mm was proposed as a default setting; not decided).
- Novelty note: mm distances alone are not new (piano tools, Rodríguez & Klapuri, Heijink);
  combining mm with string/fret choice and timing is what the survey didn't find.

### R10: decomposable cost
- Each term (shift, stretch, string crossing, …) logged separately per note pair and per hand,
  so the difficulty readout can reuse the same ergonomic profile.

### R11: instrument setup
- Setup is a whole-song choice, not part of the fingering.
- Drop tuning changes the low-string note ladder; the generator searches that neck.
- Capo: dropped as a requirement on 2026-10-04. GP capo conventions stay an open parser question.

### R12: optimality over speed
- The standard search is already exact over a whole phrase and takes milliseconds.
- Extra compute buys a richer model (more in each state, wider cost window, longer phrases),
  not more look-ahead.
  - The two-hand state is part of that: each fretting-hand state × the last stroke direction.
- Student tool option (next stage): re-finger the notes after a highlighted passage too.

### R13: licence
- Survey licence status per tool: `docs/survey/optimisers/report.md` (local).

## Design questions (not requirements)
- **Phrase / cluster definition** = core research question; designed and tested hands-on.
  - Direction: a musical unit (lick, bar), often 8/12/16/24 notes, bounded by where the hand
    has to shift far. Not a fixed number of notes ahead.
  - Open: one hand position per phrase vs up to two.
  - Chicken-and-egg: phrase cuts depend on shifts, shifts depend on cuts → choose both in one search?
  - Free starting cut points: bar lines, rests, note groupings in the GP file.
  - Soft hint (not a rule): a passage starting on an upstroke usually still belongs to the
    ongoing phrase → borders may prefer a downstroke start. R2 tracks stroke direction, so the
    hint can use it.
- **Cost terms:** case-by-case review by Jae (e.g. "pinky is expensive" is too blunt), not
  literature defaults.
- **Known traps** (survey): open-string free jumps, drift to high frets, silent note drops,
  silent hard limits, rewriting the fingering after solving.
