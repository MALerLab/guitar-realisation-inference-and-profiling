# Optimiser design log

Decisions for building GRIP's two-hand optimiser, made with Jae one topic at a time.
Requirements (what the optimiser must do): `docs/optimiser_requirements.md`. This file records
*how* we build it. Requirements win over this log in a conflict.

- Notion: updated once per finished build chunk, not per decision.
- Newest topic last. Each entry: date, decision, reason in one line.

## Guiding principle
- The optimiser does what an experienced guitarist would do when learning a passage by ear:
  they hear pitch + timing (timbre aside), hold a known guitar, and find one or more ways to
  play it. Nothing about how the tab says to play it.

## Build outline (planning order)
1. Input contract
2. Candidate positions (string, fret per note; max fret; neck geometry in mm)
3. Search skeleton (one joint search over both hands)
4. Fretting-hand state
5. Picking-hand state
6. Cost framework (terms, per-term breakdown, hard vs soft)
7. Fretting-hand cost terms
8. Picking-hand cost terms
9. Timing
10. Making many candidates
11. The "meaningful" filter
12. Test phrases + smoke tests

## 1. Input contract (2026-10-04)
- **R1 reworded** (applied in the requirements doc; Notion mirror syncs with the chunk update): "Input: monophonic note sequence
  (pitch + onset + duration per note), the tempo, and the instrument setup (R11). Nothing about
  how the source tab plays it enters generation: no fingering, technique marks or pickstroke
  marks."
  - Why: the old wording ("nothing else from the source tab") literally banned tempo and tuning,
    which R4 and R11 need.
- **Note record:** MIDI pitch, onset + duration in seconds; source ticks kept for tracing.
  - Tied notes arrive merged (parser `tied_notes: merge`) → a tie never asks for a new stroke.
- **Tempo, v1:** read the song's starting tempo from the GP file; manual override for
  hand-typed test phrases.
  - Future: follow tempo changes when the tab contains them.
- **Chords, double-stops, dead notes, v1:** each becomes a non-descript **null symbol** in the
  sequence, with the same onset + duration as what it replaces.
  - Neither hand is priced on it; both hands carry their state across it unchanged (like a rest).
  - The output marks it as a gap, so nothing is dropped silently (R8).
  - Why: refusing the whole passage would discard a solo over one double-stop; the null symbol
    is also where real chord support plugs in later.
  - Known cost: the hands cross it for free, so the cost around it is slightly too cheap.
  - Future build: chords / simultaneous notes and dead notes (picked, no pitch) get real support.

## 2. Candidate positions (2026-10-04)
- **No pruning:** every physically existing (string, fret) that sounds the pitch is a candidate,
  open strings included. Nothing is impossible by assumption (R8).
  - A note no string can reach is reported, never dropped or octave-shifted.
  - Later, maybe: explicit ground rules banning specific patterns — each one approved by Jae.
  - Jae's worry: compute time from keeping everything → answered in topic 3 (search skeleton).
- **Highest fret:** config value, default 24.
  - Why: a low default turns playable notes "impossible"; extra high candidates are ruled by cost.
- **Scale length:** config value, default 648 mm (25.5").
- **String spacing across the neck (mm):** left out; distance across = number of strings apart.
  Can return if a cost term needs it.
  - Jae (15+ years playing): never noticed spacing; what's playable on one electric is
    playable on others. His 7-string measures ≈ 41 mm at the nut, 60+ mm at the bridge
    (≈ 6.8 → 10 mm per gap, even across strings).
- **Instrument setup** = one object: per-string tuning, string count (6 or 7), highest fret,
  scale length. From the GP file or set by hand.

- **Guitar built for:** standard (single scale length). Fanned frets (per-string scale length)
  = future config option, low priority.

## 3. Search shape (in discussion, 2026-10-04)
- Jae: a guitarist thinks phrase by phrase, not note by note. A search that only judges
  neighbouring note pairs doesn't match that.
- Deferred into this discussion: search algorithm, where history lives, phrase handling.
- **Speed tooling:** plain Python + numpy first; numba only if a measured run is too slow.
- **Jae's account of learning by ear** (2026-10-04; simulated on random songs named by his wife).
  - Caveats: for guitar-idiomatic music the choice is mostly instinctive ("that lick is played
    like this"). This account is based on non-guitar vocabulary (Lingus keyboard solo, Moanin'
    sax solo, Solfeggietto on harpsichord), where he has to plan consciously.
  - Phrase first: decide how long the phrase is. Boundaries are usually obvious: musical lick
    structure, a set number of notes / beats / bars when the lick is long, or a repeating pattern.
  - Then where it's played, **relative to the current hand position**: at the 7th fret, he won't
    jump to the 15th for the next phrase just because it's easier there; moving costs more than
    finding a version that works near the current spot.
  - Place and exact shape are decided almost simultaneously; the shape isn't fixed when the place
    is chosen.
  - Takeaway: look ahead at least as far as the next phrase; stay put if you can.
  - Revision: sometimes the accepted plan for a phrase makes the next phrase harder → he reverts
    it so it fits the next one better. Each phrase bridges the previous and the next in hand
    positions (both hands: setting up the next one). Rare in guitar-idiomatic solos, more common
    the harder, more obscure or less guitar-ish the passage.
  - Offer: Jae can make the process more algorithmic by learning given examples guitar-in-hand.
- Note: the note-level exact search (Viterbi) is a time series: it scores whole-passage routes,
  not greedy picks. It never commits early, so Jae's "revert the previous phrase to set up the
  next" comes free with any exact search.
- **Search shapes considered:**
  - A. note-level: each step = one note, judged against the previous note only.
  - B. cut first, then solve: fixed cuts (bar lines, rests), each chunk solved whole, chunks linked.
  - C. segment-level: the search chooses cuts + where each chunk is played together; chunks
    scored whole (span, shape, pick pattern), moves between chunks scored separately. Inside a
    chunk, a small note-level search fills in string / finger / stroke.
- **Decision: target = C** (matches Jae's account). B = C with cuts only at bar lines / rests →
  built-in baseline.
- **Decision: build in two layers.**
  - Layer 1: note-level exact search (A), hand position + last stroke in the state, shift + timing
    costs. Also C's inner piece, so nothing is thrown away.
  - Experiment: Jae picks phrases (guitar-ish + un-guitar-ish, e.g. Moanin', Solfeggietto) and
    checks guitar-in-hand whether Layer 1 settles into licks, and where it doesn't.
  - Layer 2: chunk-level scoring for exactly the gaps the experiment shows.
  - Why: shift cost + timing may already produce much lick-like behaviour (shifts land on rests);
    what pairs can't see (whole-lick span, repeated shapes, whole-lick pick pattern, idiomatic
    shapes) gets designed from evidence, not guesses.
- **Layer 1 details:** costs compare this state with the previous one only; anything a cost
  needs to remember lives in the state. One search over the whole input passage.

## 4. Fretting-hand state (2026-10-04)
- **Decision: the hand position is its own choice in the state.** Each state holds: position
  (string, fret), the finger fretting it, and where the hand (wrist) sits on the neck.
  - Stretch = how far the finger is from its natural spot given the hand, in mm.
  - Shift = the hand position moving.
  - The hand can move during a rest, before the next phrase needs it.
  - Rejected: one finger per fret ("hand = fret − finger + 1"; reads a stretch as a shift).
  - Rejected: Jae's earlier "hand centre = average of recent finger positions". Jae: the hand
    doesn't lag behind the fingers, and a finger average doesn't describe where the wrist is;
    the hand-as-choice model is what he meant, better phrased.
- **Correction to the R3 example (Jae, 2026-10-04):** index 12 → pinky 18 is *not* nearly free;
  it's a real stretch for smaller hands (≈ 95 mm at 648 mm scale). The mm stretch cost covers it.
  Pinky 12 → index 18 is still far harder.
- **Phrase boundaries and shifts (Jae):** a pinky 12 → index 18 shift is costly mid-phrase but
  viable at a phrase boundary if the next phrase stays around the new position. Mostly how
  guitarists process things mentally, not physical capability. → input for Layer 2 and the
  timing topic (shifts cheaper at boundaries / rests).
- **Compute estimate:** ≈ 7 positions × 4 fingers × 25 hand positions × 3 strokes ≈ 2,100 states
  per note, ≈ 4.4 M comparisons per note. No pruning for speed; measure once it runs.

## 5. Picking-hand state (in discussion, 2026-10-04)
- Jae's input:
  - Leaning: down / up / none is enough to track the picking hand for the most part.
  - Pickslant / wrist angle: he thinks about it while rebuilding his technique, but not when
    normally playing.
  - Picking-hand *modes* should be tracked: hybrid picking (pick + middle / ring finger),
    right-hand tapping, right-hand harmonics (leaving the usual picking position). Taps are easy
    if the hand is already in tapping position, hard if it must switch tapping ↔ picking quickly.
- **Decision: stroke values = down / up / none / hybrid.** none = hammer-on / pull-off;
  hybrid = a middle / ring finger plucks while holding the pick ("pluck" rejected as ambiguous).
- **Decision: crossing types come from the note pair**, no extra memory: previous string +
  stroke vs current string + stroke gives sweep / inside / outside crossings and string skips.
- **Decision: pickslant / escape is never tracked.**
  - It's a player trait (makes some crossings easy for that player, e.g. 3-notes-per-string
    alternate picking), not a property of the realisation.
  - Same principle as R7 (no technique favouritism): offer every playable solution; player
    preferences re-rank the set later. Jae: this is what "technique-agnostic" originally meant.
- **Decision: picking-hand modes are all realisation options:** pick, hybrid, right-hand
  tapping, right-hand harmonics.
  - Why (Jae): leaving one out excludes the players who rely on it (e.g. hybrid picking to avoid
    string skips) — a bias, same theme as R7.
  - Tapping needs its own place on the neck (a second fretting position); switching
    tap ↔ pick costs. Right-hand harmonics change which positions sound which pitch.

- **Decision: Layer 1 = pick only** (down / up / none).
  - **Scheduled, next build chunk:** hybrid picking + right-hand tapping. State and candidate code
    keep a slot for both from day one.
  - **Parked:** right-hand harmonics and left-hand (natural) harmonics. Why (Jae): a harmonic is
    one set way of playing a specific articulation, not an alternate way of playing the notes.
- **Legato principle (R2, settled earlier):** if taking the legato away makes the passage
  harder, it's playability; otherwise it's style.

- **Jae on legato (2026-10-04, input, not yet decided):**
  - Legato is cheap compared to the picking-hand work it replaces: before a string skip, a
    legato note gives the next pick more time; a hammer-on / pull-off simplifies a complicated
    economy / sweep pattern. He uses legato for playability, almost never for style.
  - GRIP doesn't approximate the original recording, so legato is functional by default.
  - Proposal: where the source tab marks hammer-on / pull-off / bends / left-hand taps, treat the
    mark as immutable ground truth (only the neck position is free) → this reads technique marks.
  - Hammer-on from nowhere (left-hand tap): expensive, used only when no other way works, unless
    the tab marks it. Ultimate test: Tosin Abasi.
  - ⚠️ Conflicts with R1 as reworded today (no technique marks in generation) → raised with Jae.

- **Decision: articulation marks = a switch per articulation type, settable per passage.**
  - Enforced → the tab's mark is a fixed part of the music; only the neck position is free.
    Off → the mark is hidden; the articulation is decided by playability.
  - Evaluation runs hide the articulations they test; the student tool / real use enforces.
  - Jae: bends are sacred (last thing anyone turns off; a bend played as a slide isn't the same
    lick). Hammer-ons / pull-offs are usually negligible unless a strong stylistic point.
  - Applied: R1, R2, R1 + R2 + R7 details in the requirements doc; PROJECT.md invariant.
- **Decision: unenforced legato is functional**, chosen by cost where it makes the passage easier;
  ties go to picking (legato's base cost slightly above an easy pick stroke).
- **Decision: hammer-on from nowhere** (left-hand tap onto a new string / after a rest) is
  allowed, priced high, used only when nothing else works, unless enforced. Test case: Tosin
  Abasi.

- **Decision: every articulation switch defaults to enforced.**
  - Why (Jae): community tabs mark an articulation only when it's strictly or characteristically
    needed for the song, so a mark is respected. Switches exist because community tabs aren't
    always reliable.
- **Decision: bends are handled in Layer 1** (they're everywhere in solos). A bend is fretted
  below the pitch it sounds → topic 2's candidate positions must cover bent notes.
- **R2 sentence for the picking-hand modes:** applied (pick, hybrid, right-hand tapping are
  realisation options; harmonics out for now).
- **Benchmark songs** for cost tuning: `docs/benchmark_songs.md` (local file in the repo,
  gitignored).

- **Bends, as the parser gives them:** a bent note's pitch = the fretted (pressed) pitch; the
  bend is a `bend_*` tag on top. The bend-to amount isn't kept. So a bent note is placed like any
  other note; the bend doesn't change the candidate positions.
- **Decision: an open-string bend is allowed but extremely expensive** — used only when nothing
  else can produce the passage. Not a hard rule.
  - Why (Jae): it's real — *Iron Man* intro bends string 6 by pressing behind the nut — but
    letting it be cheap would turn ordinary fret-5 bends into that obscure technique.
- **Decision: bends can't be switched off until the parser keeps the bend amount** (parser to-do,
  `docs/parser_audit.md` → Parser to-dos). Bends are on by default anyway.
  - The bend amount is also needed for cost: index alone can bend a small bend, not a full one;
    larger bends need middle / ring / pinky (with support).
- **Decision: v1 articulation list** (each note carries its enforced tags; input contract field):
  - bend → the note is fretted (open string = extremely expensive, see above)
  - hammer-on / pull-off → stroke = none; same string = normal legato, a new string = hammer-on
    from nowhere (allowed, expensive). No "same string" hard rule.
  - slide → stroke = none, same string as the previous note; the hand travels with the slide
  - left-hand tap → stroke = none, any string
  - Later (ignored in v1): vibrato (needs a fretted note), let ring (overlapping notes on different
    strings), palm mute, tremolo picking, ghost notes, staccato.

## 6. Cost framework (in discussion, 2026-10-04)
- Set up regardless (Jae: "sounds good", 2026-10-04):
  - Cost term = one small named function of (previous state, current state, time between the
    notes) → a number, tagged fretting hand or picking hand.
  - Every term's value stored per note pair (R10); weights in `configs/realisation/`, never in code.
- **Awaiting Jae's explicit answers:**
  1. How costs add up over a passage: (a) plain sum · (b) worst moment (Hori) · (c) sum with big
     moves punished extra (e.g. squared). Question to Jae: does a passage feel hard by total
     effort or by its worst spot?
  2. Weights in Layer 1: (a) hand-set in config, tuned by Jae on the benchmark songs ·
     (b) learned from tab data (risk: ~79 % of DadaGP tabs match a lowest-fret rule → probably
     software-made, so learning may copy the software).
  3. Hard rules (R8): separate named list, checked apart from costs, reported by name, each one
     needs Jae's yes. Currently empty — confirm.

## Next
- Finish topic 6, then topics 7–9 (cost terms per hand, timing), then the first build plan
  (topics 1–6 + starter cost terms → one cheapest two-hand realisation for a hand-typed phrase).

## Open questions
- Topic 6 decisions 1–3 (above).
