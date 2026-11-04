# 003 - Generate the Astro feature-builder

**Status:** draft — process spec, see note below before expanding or slicing into stories.
**Depends on:** 001 (repo skeleton exists, so there is a place to scaffold `site/`).
**Reference:** `HANDOFF_dw-companion.md`, sections 4.5, 9, 10 (milestone 3 depends on this).

## Scope

This project uses the spec-to-code agent pipeline. The backend already has
`python-feature-builder` (generated from this same handoff). The frontend (`site/`, Astro +
TypeScript strict) has no equivalent agent yet, and specs 004 and 008 are frontend work that
needs one.

Before spec 004 (static site) or spec 008's widget half can be implemented through the
pipeline, run the `create-feature-builder` skill to generate `astro-feature-builder`,
mirroring how `python-feature-builder` was generated:

- Stack is already decided by the handoff (section 4.5): Astro, TypeScript strict mode, one
  interactive island for the chat widget. If `site/` still has no `package.json` when this
  runs, there is no config to detect from or precedent to read — follow the same
  "greenfield" approach used for the Python builder: state the stack from the handoff,
  confirm the agent name/scope/tooling with the user, and generate from
  `template.md` with the handoff's intentions as seed hints instead of discovered code.
- If by the time this runs `site/` already has a real Astro scaffold (e.g. spec 004 started
  manually before this), run the skill normally — real detected config and precedent always
  win over this draft's assumptions.
- Test/formatter/static-analysis commands: whatever `site/`'s `package.json` ends up using
  (likely `npm test` or none yet, Astro's check command, Prettier/ESLint if configured) —
  the handoff only mandates "TypeScript, strict mode" and lint (section 4.5, milestone 1),
  not a specific toolset; pick sensible defaults and record them.
- Must include implementation notes for: how pages are generated from
  `data/normalized/*.json`, the stable-slug rule (slugs derive from section/move IDs, never
  from display titles), the chat widget's streaming + citation-link + move-card rendering,
  and the attribution footer requirement (section 2).

## Out of scope

- Writing any actual Astro page, component, or the chat widget itself — that is specs 004
  and 008, implemented by the agent this spec produces.
- Anything about the Python backend — already covered by `python-feature-builder`.

## Note for story-creator / whoever runs this pipeline

This spec has **no application code deliverable**. Its "acceptance criteria" is an agent
file, not a tested feature, and it is not meant to be implemented by a feature-builder (an
agent cannot generate another agent for itself mid-run). When slicing this spec, either:

- turn it into a single story whose "implementation" is explicitly running the
  `create-feature-builder` skill (not `run-stage` with a feature-builder), or
- skip story-creator for this one and just run the skill directly when spec 004 or 008 is
  about to start.

## Acceptance

`.claude/agents/astro-feature-builder.md` exists, passes the skill's self-validation (no
leftover placeholders, valid YAML frontmatter, invariant sections byte-identical to
`template.md`), and the user has been told to restart the Claude Code session before the
new agent can be used.
