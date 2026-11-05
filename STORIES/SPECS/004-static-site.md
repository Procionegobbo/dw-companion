# 004 - Static rules site

**Status:** spec — ready for story-creator.
**Depends on:** 001 (`site/` npm/ESLint tooling, CI `site` job, `docs/decisions.md`), 002 (committed `data/normalized/{sections,moves,classes}.json` and their shapes), 003 (`astro-feature-builder` agent must exist before these stories are implemented — a pipeline concern only).
**Reference:** `HANDOFF_dw-companion.md` sections 2, 4.5, 10 (milestone 3).

## Feature Name & Description

**Static rules site.** An Astro (TypeScript strict) static site in `site/` that renders the whole Dungeon World rulebook from `data/normalized/*.json`: one page per section, one page per move, a table of contents, a moves index, and an attribution footer on every page. URLs derive only from `section_id` / `move_id`, so they are a stable citation target for the assistant (specs 007, 008). An automated check over the built output proves every section and move resolves to a working page and every internal link works.

**Current state.** Spec 001 (approved, not yet implemented) creates a placeholder `site/` — `package.json` with `lint` (`eslint .`) and `typecheck` (`tsc --noEmit`) scripts, strict `tsconfig.json`, flat `eslint.config.js`, `.nvmrc` (`22`), and `src/index.ts` (`export {};`) — and a CI `site` job running `npm ci`, `npm run lint`, `npm run typecheck`. Spec 002 (approved, not yet implemented) produces the three JSON files. No Astro code, page, or link check exists.

**In scope.** Astro scaffold replacing the placeholder; typed, validated data loading; URL contract; pages (home, section, moves index, move, 404); attribution footer; minimal readable CSS; Markdown rendering; unit tests (Vitest); built-output link and content check; CI steps; ADR-009; README development commands.

**Out of scope.** Chat widget and any interactive island (spec 008); visual design beyond basic readability; search; serving/deploy (spec 011); class moves as structured cards (they are not in `moves.json` — spec 002 D6).

## Assumptions & Decisions

| # | Decision | Reasoning / precedent |
|---|----------|-----------------------|
| D1 | **URL scheme (the citation contract):** section → `/rules/<section_id>/`; move → `/moves/<move_id>/`; moves index `/moves/`; home `/`. Trailing slash always. IDs are inserted verbatim (no encoding, no lowercasing) — spec 002 guarantees they match `^[a-z0-9]+(-[a-z0-9]+)*(/[a-z0-9]+(-[a-z0-9]+)*)?$` (sections) and `slugify` output (moves). | Handoff 4.5: slugs derive from IDs, never titles. Separate `/rules/` and `/moves/` prefixes avoid the collision between chapter id `moves` (`/rules/moves/`) and the moves index. Slash-containing section ids (`moves/hack-and-slash`) map directly onto nested paths, as spec 002 D5 intended. Spec 007's chunk `anchor_url` and spec 008's citation links must use exactly these formulas (recorded in ADR-009). |
| D2 | **One page per section** (including chapter root sections), not one page per chapter with fragment anchors. Section pages show breadcrumbs, child-section links and previous/next links in global `order`, so a chapter can still be read sequentially. | Draft: "a page for every section and every move". A page per URL makes the link check a file-existence check and keeps citation targets small. Spec 002 D4 keeps parent text separate from children, so no text is duplicated. |
| D3 | **Move pages in addition to section pages.** Each of the 21 moves gets `/moves/<id>/` (structured card: category, roll stat, trigger, outcome bands, full text, link to its section). The move's section page (`/rules/moves/<id>/`) links back to the card. | Draft requires a page per move; the card is what the assistant's move citations point to. Same text appears on both pages by design (spec 002: `body_markdown` = section `text_markdown`). |
| D4 | **Astro, current stable major at implementation time** (7.x on 2026-11-04, `npm view astro version` = 7.4.5), static output, `trailingSlash: "always"`, `build.format: "directory"`, no `site`/`base` set (served at domain root). No Astro integrations. | Handoff 4.5 names Astro. `directory` format gives `dist/rules/<id>/index.html`, which FastAPI/Starlette `StaticFiles(html=True)` serves and redirects slashless requests for (spec 011). The public domain is unknown until spec 011, so `site` is left unset (no canonical URLs or sitemap yet — see *Future Considerations*). |
| D5 | **Data is loaded with Vite `?raw` imports + `JSON.parse` + Zod validation in a plain module** (`site/src/lib/rulebook.ts`), not Astro content collections. | Content-collection loader and Zod import paths have changed across Astro majors; `?raw` imports are stable Vite behaviour, avoid TypeScript inferring a type from a ~MB JSON literal (slow `astro check`), and keep the loader importable from Vitest. Zod validates the cross-language contract from spec 002 at build time so drift fails the build loudly. Zod is a direct dependency (already a transitive one of Astro). |
| D6 | **Markdown rendering with `marked`** (GFM on, `breaks` off). Raw HTML tokens in the Markdown are **escaped, never passed through**. | Spec 002 emits GFM (tables, lists, blockquotes, `###`/`####`, backslash escapes). `marked` is the most widely used small Markdown library. The text is trusted pinned source, but spec 002 does not escape `<`, so escaping raw HTML costs one renderer override and removes any injection path. |
| D7 | **Tests: Vitest.** Two suites: the default `npm test` (unit tests in `site/tests/unit/`, no build needed) and `npm run check-links` (suite in `site/tests/dist/`, runs against `site/dist/` after `npm run build` and fails — not skips — if `dist/` is missing). The link checker's logic lives in `site/src/lib/link-check.ts` and is unit-tested against a synthetic `dist` fixture. | Vitest is Vite-native (same `?raw` handling as Astro), so no extra runner like `tsx` is needed for the link check. Running the check as a test suite gives readable failure output for free. Astro's container/rendering test API is avoided (version-dependent); pages are verified through built HTML instead. |
| D8 | **Tooling migration keeps spec 001's script-name contract.** `lint` stays `eslint .` (config gains `eslint-plugin-astro`); `typecheck` becomes `astro check` (covers `.astro` and `.ts` files); new scripts `dev`, `build`, `preview`, `test`, `check-links`. `site/src/index.ts` is deleted. `tsconfig.json` extends Astro's strict preset and keeps `noUncheckedIndexedAccess: true`. | Spec 001 D11 explicitly permits this. Strictness is not lowered relative to 001. |
| D9 | **`engines.node` tightens from `>=22` to `>=22.23.4`**; `site/.nvmrc` stays `22`. | `npm view astro engines` = `node >=22.23.4`. `.nvmrc` `22` resolves to the latest 22.x in CI (`actions/setup-node`), which satisfies it. Developers on an older 22.x must upgrade — called out in the README. |
| D10 | **Footer content** is the CC BY 3.0 credit, adaptation statement, SRD 5.1 / CC BY 4.0 notice, unofficial statement and MIT-for-code statement (exact copy in *Pages & Components*). No link to this project's own GitHub repository. | Handoff 2 requires credit, links to source and licence, adaptation, unofficial status and the code licence split in the footer. Spec 001 D8 established that the SRD 5.1 notice must travel with the text. The project's public repo URL is not recorded anywhere yet, so it is not invented. |
| D11 | **Null outcomes are displayed, never filled in.** `miss: null` renders "Not stated by this move." Moves with `outcomes: null` show no outcome block and "Roll: not rolled". | Spec 002 D7: inventing miss text would put words in the authors' mouths. |
| D12 | **Class chapters show a stat block** from `classes.json` (max HP, base damage, load) above their text. | Spec 002 D15 made `classes.json` "enough for site pages"; this is its only consumer here. |
| D13 | **No formatter (Prettier) yet.** | Not required by the draft or handoff; spec 001 deferred it. Kept in *Future Considerations*. |
| D14 | **`ASTRO_TELEMETRY_DISABLED: "1"`** is set as a step-level `env` in CI for Astro commands. | Avoids telemetry from CI; it is not a credential, so spec 001's "no credential-bearing env" rule holds. |

**Open risks.** (a) The JSON files are produced by spec 002; if 002 lands after 004 starts, story 1 cannot build. Story order below assumes 002 is implemented first. (b) Astro 7 API names (`astro/tsconfigs/strict`, `astro check`, `@astrojs/check`) were last verified by package availability, not by building; if the preset name differs in the installed major, use the equivalent strict preset and keep `strict` + `noUncheckedIndexedAccess` true. (c) Spec 007/008 must adopt D1's URL formulas; changing them later breaks citations.

## Architecture / Design Overview

The site is a pure build-time consumer of the committed JSON; it never imports Python or reads `vendor/`.

```
data/normalized/{sections,moves,classes}.json   (committed by spec 002)
        │  ?raw import (Vite) → JSON.parse
        ▼
site/src/lib/rulebook.ts  ── Zod schemas + integrity checks ──▶ Rulebook (indexed maps, sorted arrays)
        │                                                          │ throws RulebookError → build fails
        ▼
pages (getStaticPaths)                     site/src/lib/urls.ts (sectionUrl, moveUrl)
  /                       index.astro              │ used by every link
  /rules/<section_id>/    rules/[...id].astro  ◀───┤
  /moves/                 moves/index.astro        │
  /moves/<move_id>/       moves/[id].astro     ◀───┘
  /404.html               404.astro
        │  all wrapped in BaseLayout (header, <main>, SiteFooter)
        ▼
site/dist/**/index.html ──▶ npm run check-links (Vitest dist suite → link-check.ts)
                               every section/move page exists with its id marker,
                               every internal href/fragment resolves, footer on every page
```

`rulebook.ts` memoises the parsed result at module level so every page's `getStaticPaths` shares one parse.

## Configuration

No environment variables are read by the site.

**`site/package.json`** (modified):

| Key | Value |
|-----|-------|
| `engines.node` | `>=22.23.4` (D9) |
| `scripts.dev` | `astro dev` |
| `scripts.build` | `astro build` |
| `scripts.preview` | `astro preview` |
| `scripts.lint` | `eslint .` (unchanged) |
| `scripts.typecheck` | `astro check` (was `tsc --noEmit`) |
| `scripts.test` | `vitest run` |
| `scripts.check-links` | `vitest run --config vitest.dist.config.ts` |
| `dependencies` | `astro`, `marked`, `zod` (added with `npm install`, caret ranges) |
| `devDependencies` | existing `typescript`, `eslint`, `@eslint/js`, `typescript-eslint`; added `@astrojs/check`, `eslint-plugin-astro`, `vitest` |

`site/package-lock.json` is regenerated and committed. Every new dependency gets a one-line justification in the PR (handoff 12): astro (framework, D4), marked (D6), zod (D5), @astrojs/check (`astro check`), eslint-plugin-astro (lint `.astro`), vitest (D7).

**`site/astro.config.ts`** (new): `defineConfig({ output: "static", trailingSlash: "always", build: { format: "directory" } })`. Nothing else.

**`site/tsconfig.json`** (replaced): `extends: "astro/tsconfigs/strict"`, `compilerOptions: { noUncheckedIndexedAccess: true }`, `include: [".astro/types.d.ts", "src", "tests", "*.config.ts"]`, `exclude: ["dist"]`.

**`site/src/env.d.ts`** (new): `/// <reference types="astro/client" />` — provides `?raw` module types without depending on the generated `.astro/` directory.

**`site/eslint.config.js`** (modified): `defineConfig(js.configs.recommended, tseslint.configs.strict, eslintPluginAstro.configs.recommended, { ignores: ["dist/", ".astro/"] })`.

**`site/vitest.config.ts`** (new): `test.include: ["tests/unit/**/*.test.ts"]`, `environment: "node"`.
**`site/vitest.dist.config.ts`** (new): `test.include: ["tests/dist/**/*.test.ts"]`, `environment: "node"`.

**`.gitignore`** (modified): append `site/.astro/`.

## Data Model

No database. The site consumes spec 002's files read-only; the Zod schemas in `site/src/lib/rulebook.ts` mirror spec 002 *Data Model* exactly (spec 002 is the source of truth for field rules):

```ts
const ID_PATTERN = /^[a-z0-9]+(-[a-z0-9]+)*(\/[a-z0-9]+(-[a-z0-9]+)*)?$/; // section ids
const SLUG_PATTERN = /^[a-z0-9]+(-[a-z0-9]+)*$/;                         // move and class ids

type Stat = "STR" | "DEX" | "CON" | "INT" | "WIS" | "CHA" | "BOND" | "VARIES" | "NONE";
interface Section  { id: string; chapter: string; title: string; slug: string; parent_id: string | null; order: number; text_markdown: string }
interface Outcomes { strong_hit: string; weak_hit: string; miss: string | null }
interface Move     { id: string; name: string; category: "basic" | "special" | "class"; class: string | null;
                     stat: Stat | null; trigger: string; outcomes: Outcomes | null; body_markdown: string; section_id: string }
interface GameClass { id: string; name: string; section_id: string; order: number; max_hp_base: number; base_damage: string; load_base: number }

interface Rulebook {
  sections: readonly Section[];            // sorted by order
  moves: readonly Move[];                  // file order (Moves.xml document order)
  classes: readonly GameClass[];           // sorted by order
  sectionById: ReadonlyMap<string, Section>;
  moveById: ReadonlyMap<string, Move>;
  moveBySectionId: ReadonlyMap<string, Move>;
  classBySectionId: ReadonlyMap<string, GameClass>;
  childrenOf: ReadonlyMap<string, readonly Section[]>;  // sorted by order; every section id present (empty array if none)
}

export class RulebookError extends Error {}               // message lists every problem, one per line
export function parseRulebook(raw: { sections: unknown; moves: unknown; classes: unknown }): Rulebook;
export function loadRulebook(): Rulebook;                  // parses the three ?raw imports once, memoised
export function ancestorsOf(rb: Rulebook, id: string): readonly Section[]; // root first, excluding the section itself
```

Zod objects are `.strict()` (unknown keys are an error), so any spec 002 shape change surfaces at build time.

## Impact on Existing Code

"(new in 001)" / "(new in 002)" marks files created by approved but not-yet-implemented specs; this spec assumes they exist.

| Path | Action | Notes |
|------|--------|-------|
| `site/package.json` (new in 001) | modify — **additive for callers** | Script names `lint`/`typecheck` kept (CI contract); `typecheck` implementation changes; scripts and deps added; `engines.node` tightened (D9) — the only compatibility change, affects only developers on Node < 22.23.4. |
| `site/package-lock.json` (new in 001) | modify | Regenerated. |
| `site/tsconfig.json` (new in 001) | modify — replaced | No other file depends on it; strictness preserved (D8). |
| `site/eslint.config.js` (new in 001) | modify — **additive** | Adds Astro plugin and `.astro/` ignore; existing rule sets unchanged. |
| `site/.nvmrc` (new in 001) | unchanged | `22`. |
| `site/src/index.ts` (new in 001) | **delete** | Placeholder whose comment says it is replaced in spec 004; nothing imports it. |
| `site/astro.config.ts` (new) | create | *Configuration*. |
| `site/vitest.config.ts` (new) | create | *Configuration*. |
| `site/vitest.dist.config.ts` (new) | create | *Configuration*. |
| `site/src/env.d.ts` (new) | create | *Configuration*. |
| `site/src/lib/rulebook.ts` (new) | create | *Data Model*, *Validation Rules*. |
| `site/src/lib/urls.ts` (new) | create | *URL Contract*. |
| `site/src/lib/markdown.ts` (new) | create | *Markdown Rendering*. |
| `site/src/lib/format.ts` (new) | create | `rollLabel(stat)`, `categoryLabel(category)`, `pageTitle(title?)` — copy in *Pages & Components*. |
| `site/src/lib/link-check.ts` (new) | create | *Link Check*. |
| `site/src/layouts/BaseLayout.astro` (new) | create | *Pages & Components*. |
| `site/src/components/SiteHeader.astro` (new) | create | *Pages & Components*. |
| `site/src/components/SiteFooter.astro` (new) | create | *Pages & Components*. |
| `site/src/styles/global.css` (new) | create | *Pages & Components*. |
| `site/src/pages/index.astro` (new) | create | Home / table of contents. |
| `site/src/pages/rules/[...id].astro` (new) | create | Section pages. |
| `site/src/pages/moves/index.astro` (new) | create | Moves index. |
| `site/src/pages/moves/[id].astro` (new) | create | Move pages. |
| `site/src/pages/404.astro` (new) | create | Not-found page. |
| `site/tests/unit/rulebook.test.ts` (new) | create | *Testing*. |
| `site/tests/unit/urls.test.ts` (new) | create | *Testing*. |
| `site/tests/unit/markdown.test.ts` (new) | create | *Testing*. |
| `site/tests/unit/format.test.ts` (new) | create | *Testing*. |
| `site/tests/unit/link-check.test.ts` (new) | create | *Testing*. |
| `site/tests/dist/site.test.ts` (new) | create | *Testing*. |
| `.github/workflows/ci.yml` (new in 001) | modify — **additive** | `site` job gains steps after `npm run typecheck`: `npm test`, `npm run build`, `npm run check-links`; `env: ASTRO_TELEMETRY_DISABLED: "1"` on the `typecheck`, `build` steps. Existing steps, triggers, permissions and the `python` job unchanged; still no `secrets.` (spec 001's `test_ci_workflows_reference_no_secrets` keeps passing). |
| `.gitignore` (new content from 001) | modify — **additive** | Append `site/.astro/`. |
| `docs/decisions.md` (new in 001) | modify — **additive** | Append ADR-009 (*Documentation*). |
| `README.md` (new in 001) | modify — **additive** | *Documentation*. The `## Attribution` section is untouched, so spec 001's README compliance test is unaffected. |
| `data/normalized/*.json` (new in 002) | read only | Never written by the site. |

## URL Contract

`site/src/lib/urls.ts` is the only place URLs are built; every page and component uses it.

```ts
export const HOME_URL = "/";
export const MOVES_INDEX_URL = "/moves/";
export function sectionUrl(sectionId: string): string; // `/rules/${sectionId}/`
export function moveUrl(moveId: string): string;       // `/moves/${moveId}/`
```

Both functions throw `Error` if the id does not match its pattern (*Data Model*), so a malformed id cannot produce a broken URL silently. No title, slug or display text ever contributes to a URL.

## Markdown Rendering

`site/src/lib/markdown.ts` exports `renderMarkdown(markdown: string): string` (HTML) using a dedicated `Marked` instance (not the global one) with `gfm: true`, `breaks: false`, and a renderer override for `html` tokens that returns the token text HTML-escaped (`&`, `<`, `>`, `"`, `'`). Empty input returns `""`. Pages insert the result with `set:html`. Heading levels inside the text (`###`, `####`) are kept as-is.

## Pages & Components

All pages use `BaseLayout.astro` (props: `title?: string`).

**`BaseLayout.astro`**: `<html lang="en">`, `<meta charset="utf-8">`, viewport meta, `<title>` = `pageTitle(title)`: `"<title> · Dungeon World Companion"`, or `"Dungeon World Companion (unofficial)"` when no title. Imports `global.css`. Body: a skip link `<a class="skip-link" href="#main">Skip to content</a>`, `<SiteHeader />`, `<main id="main">` slot, `<SiteFooter />`.

**`SiteHeader.astro`**: `<header>` with the site name link "Dungeon World Companion" → `HOME_URL`, and `<nav aria-label="Main">` with links "Contents" → `/` and "Moves" → `/moves/`. The link matching the current page has `aria-current="page"`.

**`SiteFooter.astro`** — `<footer>` with exactly this copy (links as shown):

> Rules text: *Dungeon World* by Sage LaTorra and Adam Koebel, from [github.com/Sagelt/Dungeon-World](https://github.com/Sagelt/Dungeon-World), licensed under [Creative Commons Attribution 3.0 Unported (CC BY 3.0)](https://creativecommons.org/licenses/by/3.0/). The text has been adapted: parsed from the source XML and reformatted for the web.
>
> This work includes material taken from the System Reference Document 5.1 ("SRD 5.1") by Wizards of the Coast LLC, licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/legalcode).
>
> This is an **unofficial** fan project, not affiliated with or endorsed by the authors or publishers of Dungeon World. The site's source code is licensed under the MIT License.

External links in the footer use `rel="license"` on the two licence links.

**`global.css`**: system font stack, `max-width: 42rem` centred content, `line-height: 1.6`, readable table borders, visible focus outlines, `.skip-link` hidden until focused. No colour theme, no web fonts, no JS.

**`index.astro` (`/`)** — `title` none. `<h1>Dungeon World Companion</h1>`; paragraph "The complete Dungeon World rules, reformatted for the web. Unofficial — see the footer for credits and licence."; `<h2>Chapters</h2>` with an `<ol>` linking every section whose `parent_id` is `null`, in `order`, text = section title; `<h2>Moves</h2>` with paragraph linking "Basic and special moves" → `/moves/`.

**`rules/[...id].astro` (`/rules/<section_id>/`)** — `getStaticPaths` returns one entry per section: `params: { id: section.id }`, `props: { section }`. Content in order:
1. `<nav aria-label="Breadcrumb">` with an `<ol>`: "Contents" → `/`, then each ancestor (root first) linked by title, then the current title as plain text with `aria-current="page"`.
2. `<article data-section-id="<id>">` containing `<h1>` = title.
3. If `classBySectionId` has the section: `<dl class="class-stats">` with `Max HP` → `<max_hp_base> + Constitution`, `Base damage` → `<base_damage>`, `Load` → `<load_base> + Str`.
4. If `moveBySectionId` has the section: `<p>` "Move card: " + link `<move name>` → `moveUrl`.
5. `renderMarkdown(text_markdown)`.
6. If the section has children: `<h2>In this section</h2>` + `<ul>` of child links (titles, in order).
7. After the article, `<nav aria-label="Previous and next">`: "← <previous title>" and "<next title> →" linking the sections immediately before / after this one in the `order`-sorted `sections` array; each link is omitted at its end of the book.

**`moves/index.astro` (`/moves/`)** — `title` "Moves". `<h1>Moves</h1>`; one group per category present, in the order basic, special, class, headed `<h2>` "Basic moves" / "Special moves" / "Class moves"; each a `<ul>` of items: link (move name) → `moveUrl`, followed by " — " and the trigger text.

**`moves/[id].astro` (`/moves/<move_id>/`)** — `getStaticPaths` over `moves`. `title` = move name. Breadcrumb: "Contents" → `/`, "Moves" → `/moves/`, current name. `<article data-move-id="<id>">`:
1. `<h1>` = name; `<p>` = `categoryLabel(category)` ("Basic move" / "Special move" / "Class move").
2. `<dl class="move-facts">`: `Trigger` → trigger text; `Roll` → `rollLabel(stat)`.
3. If `outcomes` is not null: `<h2>Outcomes</h2>` and `<dl class="outcomes">` with `10+ (strong hit)` → rendered `strong_hit`, `7–9 (weak hit)` → rendered `weak_hit`, `6- (miss)` → rendered `miss` or "Not stated by this move." when null (D11).
4. `<h2>Full text</h2>` + `renderMarkdown(body_markdown)`.
5. `<p>` "Read it in the rules: " + link (section title) → `sectionUrl(section_id)`.

`rollLabel`: `STR`…`CHA` → `"+STR"` … `"+CHA"`; `BOND` → `"+Bond"`; `VARIES` → `"+stat chosen by how you act"`; `NONE` → `"2d6, no stat added"`; `null` → `"Not rolled"`.

**`404.astro`** — `title` "Page not found". `<h1>Page not found</h1>`; "There is no page at this address." and link "Go to the contents" → `/`.

## Link Check

`site/src/lib/link-check.ts`:

```ts
export interface LinkCheckReport { pages: number; internalLinks: number; problems: readonly string[] }
export function checkSite(distDir: string, rb: Rulebook): LinkCheckReport;
```

Rules (each failure appends one human-readable problem naming the file and the offending href/id):

1. **ID coverage:** for every section, `<dist>/rules/<id>/index.html` exists and contains `data-section-id="<id>"`; for every move, `<dist>/moves/<id>/index.html` exists and contains `data-move-id="<id>"`. `<dist>/index.html`, `<dist>/moves/index.html` and `<dist>/404.html` exist.
2. **Internal links:** every `href="…"` in every `*.html` under `dist` is classified: `http:`, `https:`, `mailto:` → external, skipped (not fetched); `#frag` → the same file must contain `id="frag"`; starting with `/` (not `//`) → strip query, split fragment, decode `&amp;`; path ending `/` must have `<path>index.html`; any other path must be an existing file (if only `<path>/index.html` exists, report "missing trailing slash"); if a fragment is present, the target HTML must contain `id="<frag>"`; anything else (relative path, `//host`) → problem "non-root-relative link".
3. **Footer:** every HTML file contains `https://creativecommons.org/licenses/by/3.0/`, `https://github.com/Sagelt/Dungeon-World` and `unofficial`.

`internalLinks` counts checked internal hrefs; `pages` counts HTML files. Pure Node `fs`/`path`, no HTTP server, no network.

## Validation Rules

No user input. Build-time rules enforced by `parseRulebook` (all problems are collected, then one `RulebookError` is thrown, which fails `astro build`):

| Subject | Rule |
|---------|------|
| Shapes | Each file is a JSON array; every element matches its strict Zod schema (*Data Model*): exact keys, types, enums (`category`, `stat`), `outcomes` null or all three keys present. |
| Section `id` | Matches `ID_PATTERN`; unique. |
| Section `title` | Non-empty after trim. |
| Section `order` | Integers, unique. |
| Section `parent_id` | `null` or an existing section id. |
| Move `id`, class `id` | Match `SLUG_PATTERN`; unique within their file. |
| Move `section_id`, class `section_id` | Existing section id. |
| Move `trigger`, `name` | Non-empty after trim. |
| `max_hp_base`, `load_base` | Positive integers. `base_damage` matches `^d\d+$`. |
| URLs | All `sectionUrl`/`moveUrl` results distinct (guaranteed by unique ids and disjoint prefixes; asserted in tests). |

## Authorization & Security

No users, endpoints, forms or client-side JavaScript; the site is public static HTML.

- Raw HTML in Markdown is escaped (D6); all other dynamic text goes through Astro's default escaping. `set:html` is used only with `renderMarkdown` output.
- The build reads only `data/normalized/*.json`; nothing from `vendor/` (spec 001 D10).
- CI remains read-only and secret-free (spec 001 D12); the link check makes no network requests.

## Documentation

**`docs/decisions.md`** — append **ADR-009: Static site: Astro, URL contract, data loading and link check** (spec 001 D15 format), content from D1–D8 and D10. It must state the URL formulas `/rules/<section_id>/` and `/moves/<move_id>/` verbatim and that specs 007 (`anchor_url`) and 008 (citation links, move card) must use them; and that it extends ADR-005 (placeholder tooling), whose `lint`/`typecheck` script names are kept.

**`README.md`** — in `## Development`, replace the three-line site command block with: `npm ci`, `npm run dev` (local server), `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`, `npm run check-links` (after build); change "Node 22" in the requirements line to "Node 22.23.4 or newer 22.x". No other section changes.

## Testing

Vitest, files under `site/tests/`, plain `describe`/`it`, `node:fs` temp dirs via `fs.mkdtempSync(os.tmpdir())` for fixtures. All offline and deterministic. Tests build small valid fixtures with a local helper (`validSection(overrides)`, `validMove(overrides)`, `validClass(overrides)`) inside each test file that needs them.

**`tests/unit/rulebook.test.ts`**
- `loads the committed data without errors` — `loadRulebook()` returns 21 moves, 8 classes, ≥ 37 sections, 37 sections with `parent_id === null`.
- `sorts sections by order` and `childrenOf lists children in order`.
- `indexes moves by section id` — `moveBySectionId.get("moves/hack-and-slash")?.id === "hack-and-slash"`.
- `indexes classes by section id` — `classBySectionId.get("fighter")?.base_damage === "d10"`.
- `ancestorsOf returns root first` — `moves/hack-and-slash` → `["moves", "moves/basic-moves"]`.
- `rejects unknown keys` — extra field on a section → `RulebookError`.
- `rejects a dangling parent_id`, `rejects a move whose section_id does not exist`, `rejects duplicate section ids`, `rejects a malformed section id` (`Moves/Hack`), `rejects an invalid stat` (`"LUCK"`), `rejects outcomes missing the miss key`.
- `reports every problem in one error` — two independent defects → message contains both.

**`tests/unit/urls.test.ts`**
- `builds section urls from ids` — `fighter` → `/rules/fighter/`; `moves/hack-and-slash` → `/rules/moves/hack-and-slash/`.
- `builds move urls from ids` — `hack-and-slash` → `/moves/hack-and-slash/`.
- `rejects ids that do not match the pattern` — `Hack and Slash`, `../x` and the empty string → throw.
- `every committed section and move maps to a distinct url` — over `loadRulebook()`.

**`tests/unit/markdown.test.ts`**
- `renders emphasis and strong`, `renders bulleted and numbered lists`, `renders a GFM table` (`| Score | Modifier |` → `<table>` with `<th>Score</th>`), `renders blockquotes and h4 headings`.
- `unescapes backslash escapes` — `b\[2d6\] \_\_` → text `b[2d6] __`.
- `escapes raw html` — `<script>alert(1)</script>` → output contains `&lt;script&gt;` and no `<script>`.
- `returns empty string for empty input`.

**`tests/unit/format.test.ts`**
- `rollLabel maps every stat` — table over all nine values plus `null` per *Pages & Components*.
- `categoryLabel maps every category`.
- `pageTitle with and without a title`.

**`tests/unit/link-check.test.ts`** (synthetic `dist` in a temp dir, synthetic rulebook via `parseRulebook`)
- `passes a complete site` — zero problems; counts correct.
- `reports a missing section page`, `reports a page without its id marker`, `reports a missing move page`.
- `reports a broken internal link`, `reports a missing trailing slash`, `reports a missing fragment target`, `reports a relative link`.
- `skips external links`.
- `reports a page without the attribution footer`.

**`tests/dist/site.test.ts`** (run by `npm run check-links`; `beforeAll` throws "site/dist not found: run `npm run build` first" if `dist/index.html` is missing)
- `every section_id and move_id resolves and every internal link works` — `checkSite("dist", loadRulebook()).problems` equals `[]` (the milestone 3 acceptance check; failure prints the problem list).
- `home links every chapter` — `dist/index.html` contains `href="/rules/<id>/"` for all 37 root sections.
- `moves index links every move` — 21 `href="/moves/<id>/"`.
- `hack-and-slash card shows trigger, roll, bands and unstated miss` — contains `When you attack an enemy in melee`, `+STR`, `10+ (strong hit)`, `Not stated by this move.`, and `href="/rules/moves/hack-and-slash/"`.
- `last-breath card shows its miss` — contains `On a miss, your fate is sealed.` and `2d6, no stat added`.
- `encumbrance card has no outcomes block` — contains `Not rolled`, not `10+ (strong hit)`.
- `move section links back to its card` — `dist/rules/moves/hack-and-slash/index.html` contains `href="/moves/hack-and-slash/"`.
- `breadcrumbs list ancestors` — same file contains `href="/rules/moves/"` and `href="/rules/moves/basic-moves/"`.
- `fighter chapter shows class stats` — `dist/rules/fighter/index.html` contains `Max HP`, `10 + Constitution`, `d10`, `12 + Str`.
- `stat table renders as html table` — at least one `index.html` under `dist/rules/character-creation/` (the chapter page or any descendant section page) contains `<table>` and `<th>Score</th>`.
- `every page declares lang and has a main landmark` — every HTML file contains `<html lang="en"` and `id="main"`.

**Manual / CI verification:** `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`, `npm run check-links` exit 0; open `npm run dev` once and click through home → chapter → section → move card.

## Suggested Story Breakdown

1. **Astro scaffold, data layer, layout and home** — package/tsconfig/ESLint/Vitest/Astro config migration, delete placeholder, `.gitignore`, `rulebook.ts`, `urls.ts`, `format.ts`, `BaseLayout`, `SiteHeader`, `SiteFooter`, `global.css`, `index.astro`, `404.astro`; unit tests for rulebook, urls, format; CI steps `npm test` and `npm run build`; ADR-009. Verifiable: build produces `dist/index.html` with footer and chapter list. Depends on specs 001, 002, 003.
2. **Section pages** — `markdown.ts` + tests, `rules/[...id].astro` (breadcrumbs, class stats, children, prev/next; the move-card link is added in story 3). Depends on 1.
3. **Move pages** — `moves/index.astro`, `moves/[id].astro`, move-card link on section pages. Depends on 2.
4. **Link check and close-out** — `link-check.ts` + unit tests, `vitest.dist.config.ts`, `tests/dist/site.test.ts`, `check-links` script, CI step, README update. Depends on 3.

## Success Criteria

- [ ] `npm ci && npm run lint && npm run typecheck && npm test && npm run build && npm run check-links` in `site/` exits 0.
- [ ] `npm run check-links` reports zero problems: every `section_id` resolves to `/rules/<section_id>/` and every `move_id` to `/moves/<move_id>/`, and every internal link works (milestone 3 acceptance).
- [ ] Every test listed in *Testing* exists and passes.
- [ ] Every built page carries the footer with the CC BY 3.0 source and licence links, adaptation, SRD 5.1 notice, unofficial and MIT statements.
- [ ] No URL in `site/src/` is built outside `urls.ts` from anything but an id (review check: `grep -rn '"/rules/\|"/moves/' site/src` finds only `urls.ts`).
- [ ] CI `site` job runs lint, typecheck, test, build and check-links green on a PR; `ci.yml` still contains no `secrets.`.
- [ ] `site/src/index.ts` no longer exists; `docs/decisions.md` contains ADR-009 with the URL formulas.

## Future Considerations

- Set Astro `site` once spec 011 fixes the public domain, then add canonical links and a sitemap.
- Prettier (or another formatter) for `site/`.
- Client-side search over section titles.
- Link to this project's GitHub repository and `ATTRIBUTION.md` from the footer once the public repo URL is fixed.
- A Python-side test (spec 007) asserting `anchor_url` equals `/rules/<section_id>/`, so both sides of the URL contract are guarded.
