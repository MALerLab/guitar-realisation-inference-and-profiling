# PROJECT.md — guitar-realisation-inference-and-profiling (GRIP)
<!-- Stable project facts for any coding agent. Claude Code reads this via CLAUDE.md,
     Codex via AGENTS.md. Agent-specific behaviour lives in those files, not here. -->

## What belongs here vs Notion
- **Here:** what a coding agent would get wrong without it — environment, folder rules,
  code vocabulary, invariants the code must enforce, data locations, verified gotchas.
- **Notion:** the why and the what-next — project definition, reasoning, roadmap/status,
  decisions + options considered, results, survey.
- **Overlap:** state the rule here in one line + a Notion link; the reasoning lives in Notion.
- **Conflict:** Notion wins on plan; this file wins on repo facts (checked against code).
- **Bloat:** long detail → `docs/*.md`, linked from here.

## Notion
- Hub: **guitar-realisation-inference-and-profiling** — `3e3cb37787438058920dfb43c0fed996`
- **Project Definition** — `3e2cb3778743805695c9f06c05097979`
- Read the hub before any planning or status work.

## Environment
- `uv` project, Python 3.11. Never `pip install`.
- Node side (alphaTab, for `src/data/gp_parser.py`): after `uv sync`, run `uv run npm ci` once per
  clone. `node_modules/` is untracked; `package-lock.json` pins alphaTab.

## Git remotes
- One remote, `origin`: fetch from one URL, push to two. Both repos are **public**.
  - fetch: `git@github.com:jae-gye/guitar-realisation-inference-and-profiling.git`
  - push: the same URL + `git@github.com:MALerLab/guitar-realisation-inference-and-profiling.git`
- One `git push` updates both; there is no separate MALerLab remote to fetch from.
- Check: `git remote -v` → 1 fetch line, 2 push lines.

## Layout rules
- `src/` subpackages: `data/` · `realisation/` · `technique/` · `evaluation/`.
- `configs/<subpackage>/` mirrors `src/<subpackage>/` — no hardcoded parameters in `src/`.
  `configs/experiments/` is added when the first experiment exists.
- `scripts/` = one-off / temporary, **untracked**. May hardcode values; its settings never
  enter `configs/`. Used twice or proven useful → review and promote to `src/`.
- `manifests/*.parquet` = tracked source of truth, **indexes only** — ids, paths, splits,
  metadata. Never musical content (notes, string/fret, techniques). CSV only on demand,
  never tracked.
- **Derived datasets** = anything holding musical content → `~/storage/...`, untracked.
  The repo is public: nothing from DadaGP / mySongBook may be committed.
- `data/` = symlinks to `~/storage/...`, untracked.
- `externals/<category>/<repo>` = reused repos as git submodules, pinned to release tags,
  read/reference only, unmodified (e.g. `externals/parsers/PyGuitarPro`). Large repos are
  shallow (`shallow = true` in `.gitmodules`). Clone with `--recurse-submodules`.
- `experiments/`: `exp<NNN>_<YYMMDD>_<rest>`.

## Vocabulary (one word per concept, in code and docs)
- **realisation** — one fret/string path for a fixed pitch + timing passage.
- **technique compatibility** — which techniques a realisation supports.
- **reference coverage** — does the candidate set contain the trusted human realisation,
  or something materially similar?
- **technique coverage** — does ≥1 plausible candidate preserve the withheld technique?

## Invariants
- Generate → freeze candidates → analyse techniques. Generation is technique-agnostic.
  - `src/realisation/` never imports from `src/technique/` or `src/evaluation/`.
  - Source fingering/technique never chooses positions; compatibility scores never steer
    generation.
- Source fingering = evidence, not target. Reference coverage is not the evaluation target.
- Missing annotation ≠ negative label (incl. absent DadaGP technique tokens).
- mySongBook data is never redistributed.

## Data on disk
_(empty until data arrives)_

## Gotchas
_(verified facts only)_
