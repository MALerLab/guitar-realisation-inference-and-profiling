# Repository agent entrypoint

## Survey work

Before any survey search, source screening, evidence extraction, synthesis, or survey-related
write, read these files in order:

1. `PROJECT.md`
2. `docs/survey/protocol.md`
3. `docs/survey/schema.md`
4. The active run log under `docs/survey/`

The current protocol is **Survey Protocol v0.1**. Do not silently change its scope, quotas,
stopping rules, evidence labels, or right-hand requirements. Record ambiguities in the run log
for coordinator review.

Survey workers must keep their outputs within their assigned strand, use the shared schema, and
must not edit the Notion hub, commit, push, or modify another worker's output without explicit
coordinator authorisation.
