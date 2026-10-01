# GRIP Survey Protocol v0.1

**Project:** guitar-realisation-inference-profiling (GRIP)  
**Status:** active survey run; v0.1 scope frozen
**Protocol version:** 0.1  
**Owner:** root/coordinator agent, with Jae as decision authority  
**Current run:** `docs/survey/run-2026-09-30.md`

## 1. Purpose

Establish the defensible research gap around symbolic guitar execution:

> Given fixed pitch and timing, has prior work generated multiple playable guitar realisations,
> modelled both hands' execution demands, analysed technique compatibility, and estimated
> difficulty over the alternative realisation set?

The survey must test the project's novelty rather than assume it. A source may cover one part of
the pipeline without covering the full combination.

## 2. Project invariants

- Treat source tablature as evidence for pitch and timing, not canonical string/fret placement.
- Distinguish one realisation from a set of alternative realisations.
- Distinguish physical feasibility, ergonomic playability, technique compatibility, and difficulty.
- Generation and technique analysis remain conceptually separate: generate first, freeze candidates,
  then analyse compatibility.
- Technique is descriptive, not a claim about the original performer's historical intent.
- Missing annotation is not a negative technique label.
- Exact historical fingering recovery is not the evaluation target.

## 3. Scope

### Include

- Symbolic guitar, tablature, MIDI-to-tab, string/fret assignment, and guitar fingering systems.
- Guitar playability, ergonomic, physical-demand, and difficulty models.
- Picking-hand and guitar-technique modelling.
- Technique-aware generation or post-hoc technique analysis.
- Datasets, annotations, and human-evaluation methods relevant to symbolic execution.
- Commercial systems and open-source projects that generate or assess guitar execution.

### Include as adjacent precedent

- Piano, violin, bass, or other string-instrument work involving physical costs, alternative
  realisations, difficulty estimation, or expert pairwise evaluation.

### Treat as contextual unless it informs symbolic execution

- Audio-only technique recognition.
- General guitar advice without an explicit method or evidence.
- Products that only display or transcribe tabs without modelling execution, playability, or difficulty.

## 4. Strand ownership

Each source receives one primary strand owner and may receive multiple cross-tags.

1. **Symbolic realisation:** guitar fingering, fret/string assignment, MIDI-to-tab, candidate paths.
2. **Playability and difficulty:** left-hand ergonomics, physical demand, placement-aware difficulty.
3. **Right-hand technique:** pick direction, strict alternate, economy, sweep, string crossings,
   skips, re-attacks, and interaction with legato.
4. **Data and evaluation:** technique labels, datasets, recovery tests, expert judgement, agreement.
5. **Commercial systems:** products, documented features, demonstrations, and practical limitations.
6. **Open-source engineering:** repositories, released tools, implementations, licences, and code evidence.
7. **Community practice:** guitarist terminology, technique heuristics, and real-world constraints.
8. **Adjacent methods:** non-guitar methodological precedents not naturally owned by strands 1–4.

The coordinator owns deduplication, cross-strand conflicts, synthesis, and novelty claims.

## 5. Search protocol

Each strand begins with a short scout pass to identify terminology and anchor sources. The scout is
seed generation, not a stopping rule.

Use four query families, adapted to the strand:

1. **Representation:** guitar tablature, symbolic guitar, MIDI-to-tab, guitar fingering,
   string-fret assignment, fretboard realisation.
2. **Playability:** guitar playability, guitar difficulty, fretboard ergonomics, hand stretch,
   position shift, physical demand.
3. **Right hand:** pick direction, alternate picking, economy picking, sweep picking,
   string crossing, string skip, picking pattern.
4. **Technique and evaluation:** guitar technique annotation, technique compatibility,
   performance difficulty, expert judgement, human evaluation.

For academic sources, search the declared scholarly sources and screen a fixed result set for each
query family. Expand from strong sources through backward and forward citations for up to two rounds.
Record the search date and exact query in the active run log.

## 6. Coverage targets

The initial academic target is **50 unique in-scope scholarly records**, allocated as follows:

- 15 symbolic realisation/fingering records;
- 12 playability/difficulty records;
- 12 right-hand/technique records;
- 6 data/evaluation records;
- 5 adjacent methodological precedents.

Initial non-academic targets are:

- 15 commercial systems;
- 25 open-source repositories or engineering projects;
- 20 community discussions or practice sources.

Targets are coverage commitments, not permission to include irrelevant sources. Every direct
competitor or serious novelty counterexample is included even if a target is exceeded.

## 7. Stopping rules

A strand may stop its broad search only when:

1. its minimum target is met or the declared search universe is exhausted;
2. all four relevant query families have been attempted;
3. up to two citation-expansion rounds have been attempted; and
4. two consecutive expansion rounds produce no new close competitor or major counterexample.

The coordinator may reopen a strand when another strand reveals new terminology, a new citation
hub, or a plausible counterexample.

## 8. Right-hand requirements

Every potentially relevant source must be checked for explicit evidence of:

- pick-direction sequence;
- strict alternate picking;
- economy picking;
- sweep picking;
- string crossings and string skips;
- repeated-string attacks and re-attacks;
- hammer-ons, pull-offs, and their effect on right-hand demand;
- phrase-level or stateful modelling;
- right-hand ergonomic cost;
- whether right-hand information affects generation, analysis, difficulty, or only labelling.

Technique labels are not assumed to be mutually exclusive. A realisation may support more than one
technique, and economy and sweep terminology must be reported using the source's operational
definition.

## 9. Evidence rules

- Do not treat a title, search snippet, repository name, or marketing claim as method evidence.
- For every source, attempt to obtain and inspect the full primary source: paper, thesis, official
  documentation, released code, product documentation, or the most authoritative equivalent.
- If the full source cannot be obtained, record exactly what was used instead, such as an abstract,
  author manuscript, repository README, official project page, metadata record, product page, or
  community discussion. State what could and could not be verified from that fallback.
- Make the source explicit for every claim, regardless of strand or source type.
- Record a section, page, figure, code path, or quoted passage for material claims.
- For accessible papers and other full sources, collect a local copy under `docs/literature/` when
  redistribution is permitted. If redistribution is not permitted, record the canonical URL and
  access note without copying the source into the repository.
- The final report must list useful sources whose full text was unavailable, including the source
  used instead, why the full source was inaccessible, what remains unverified, and the canonical URL.
- Distinguish `verified absent`, `not reported`, `not checked`, and `unclear`.
- Do not convert missing technique annotation into a negative technique label.
- Do not claim field-wide absence from one failed search.

## 10. Worker contract

Every worker must:

1. read this protocol and `docs/survey/schema.md` before searching;
2. state the protocol version and assigned strand in its output;
3. use the shared evidence schema;
4. keep a source ledger, not just a prose summary;
5. flag overlap, ambiguity, and possible counterexamples;
6. stop and ask the coordinator when a protocol rule is insufficient;
7. avoid changing the protocol, Notion, or another worker's files.

Workers should write only to their assigned strand output. The coordinator performs integration.

## 11. Orchestration gates

- **Calibration gate:** test the schema with symbolic-realisation and right-hand strands first.
- **Academic gate:** launch playability, data/evaluation, and adjacent strands after calibration.
- **Applied gate:** launch commercial, open-source, and community strands after the academic schema
  is stable.
- **Red-team gate:** search specifically for counterexamples to the emerging novelty claim.
- **Synthesis gate:** integrate only verified records and clearly label uncertainty.

No survey search or subagent deployment occurs merely because these files exist. The coordinator
requires Jae's explicit go-ahead for the active run.

## 12. Change control

Any change to scope, terminology, quotas, stopping rules, or evidence labels requires:

- a protocol version increment;
- a short rationale in the active run log;
- coordinator review of already-produced records;
- explicit approval before affected workers resume.

Notion remains the human-facing record of project rationale, decisions, status, and results. Notion
updates are separate from repository edits and require explicit confirmation.
