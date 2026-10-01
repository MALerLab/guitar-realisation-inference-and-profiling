# GRIP Survey Evidence Schema v0.1

Use one record per source. A source may have multiple evidence rows only when it contains clearly
separate systems or studies.

## 1. Required source fields

| Field | Required content |
|---|---|
| `record_id` | Stable local identifier, for example `PAP-001` or `GH-004` |
| `primary_strand` | One protocol strand owner |
| `cross_tags` | Additional relevant strands or concepts |
| `source_type` | Paper, thesis, dataset, product, repository, community, or adjacent precedent |
| `title` | Exact source title |
| `authors_or_owner` | Authors, organisation, or account name |
| `year_or_access_date` | Publication year or access date |
| `canonical_url` | DOI, official page, repository, or stable permalink |
| `source_status` | Discovery, screened, included, verified, or nearest-neighbour |
| `relevance_tier` | A, B, or C |
| `access_status` | Full source inspected, full source obtained but not redistributable, partial source, metadata only, or unavailable |
| `source_used_for_claims` | Exact source actually consulted for the recorded claims |
| `accessibility_note` | Access route, failure reason, and remaining verification limits |
| `literature_artifact` | Path under `docs/literature/`, or `not_stored` with the reason |
| `evidence_location` | Page, section, figure, code path, timestamp, or quoted passage |
| `confidence` | High, medium, or low |

## 2. Research-object fields

| Field | Allowed values or guidance |
|---|---|
| `input_representation` | Pitch/timing, tablature, MIDI, audio, symbolic score, mixed, unclear |
| `output_representation` | One placement, multiple placements, technique labels, difficulty score, profile, other |
| `candidate_multiplicity` | One, multiple, k-best, ranked set, unclear, not applicable |
| `left_hand_model` | Explicit, partial, indirect, absent, not reported, unclear |
| `right_hand_model` | Explicit, partial, indirect, absent, not reported, unclear |
| `phrase_context` | Note-local, phrase-level, sequence/stateful, unclear |
| `difficulty_target` | Written placement, generated placement, realisation set, general performance, none, unclear |
| `generation_analysis_relation` | Generation uses technique, post-hoc analysis, joint model, not applicable, unclear |
| `evaluation_method` | Held-out data, exact match, coverage, expert judgement, pairwise judgement, user study, none, unclear |
| `data_and_annotation` | Dataset name, annotation type, scale, licence/access, and known limitations |
| `code_status` | Open, partial, available on request, closed, unavailable, not applicable |

## 3. Technique fields

Use `compatible`, `partial`, `incompatible`, `not reported`, `unclear`, or `not applicable` only
when the source supports that judgement.

- `strict_alternate`
- `economy`
- `sweep`
- `legato`
- `other_techniques`
- `technique_definition`
- `technique_evidence`

For `economy` and `sweep`, copy the source's operational definition or state that the terminology
was inferred. Do not collapse overlapping labels into one category.

## 4. Relevance tiers

- **Tier A — direct competitor:** covers at least two core GRIP dimensions and could challenge the
  central novelty claim.
- **Tier B — close component:** covers one core dimension strongly or supplies an important method,
  dataset, taxonomy, or evaluation precedent.
- **Tier C — context:** useful for terminology, history, motivation, or broad landscape only.

## 5. Evidence-status vocabulary

- **Verified present:** directly supported by the source.
- **Verified absent:** the method or artefact was checked and does not contain the feature.
- **Not reported:** the inspected source does not state whether the feature exists.
- **Not checked:** the source still requires inspection.
- **Unclear:** evidence is conflicting, ambiguous, or inaccessible.

Never rewrite `not reported` as `absent`.

## 6. Source-accessibility vocabulary

- **Full source inspected:** The complete authoritative source was obtained and checked.
- **Full source obtained but not redistributable:** The complete source was inspected but is not
  copied into the repository because access or licence terms do not permit redistribution.
- **Partial source:** An author manuscript, accepted version, excerpt, abstract, repository README,
  official documentation, or other incomplete source was inspected.
- **Metadata only:** Only bibliographic metadata or an index record was available.
- **Unavailable:** A useful source was identified, but no substantive source could be inspected.

For every status except `full source inspected`, write an accessibility note. A fallback source may
support discovery and cautious contextual claims, but it cannot support unverified method details.

Accessible full papers should be stored under `docs/literature/` when redistribution is permitted.
Otherwise store the citation, canonical URL, access status, and reason for non-storage.

The final report must contain an **inaccessible useful sources** list with:

- citation and canonical URL;
- why the source appeared relevant;
- access status and attempted access route;
- fallback source actually consulted, if any;
- information that remains unverified;
- whether the source could threaten a novelty claim.

## 7. Worker handoff template

```markdown
## Source: [record_id] — [title]

- Protocol: v0.1
- Primary strand:
- Cross-tags:
- Relevance tier:
- Source status:
- Canonical URL:
- Access status:
- Source used for claims:
- Accessibility note:
- Literature artifact:
- Input:
- Output:
- One or multiple realisations:
- Left-hand model:
- Right-hand model:
- Phrase-level/stateful analysis:
- Strict alternate:
- Economy:
- Sweep:
- Legato:
- Difficulty target:
- Evaluation:
- Data and annotation:
- Code/access:
- Evidence location:
- Confidence:
- GRIP relevance:
- Open question or counterexample:
```

## 8. Strand summary template

Each strand report must end with:

- records discovered;
- records screened;
- records included;
- records verified;
- full sources inspected;
- useful sources with inaccessible full text;
- Tier A direct competitors;
- important negative or counterexample findings;
- terminology discovered;
- unresolved ambiguities;
- recommendation for the coordinator.
