import { z } from "zod";
import sectionsRaw from "../../../data/normalized/sections.json?raw";
import movesRaw from "../../../data/normalized/moves.json?raw";
import classesRaw from "../../../data/normalized/classes.json?raw";

// Mirrors spec 002's ingestion output shapes exactly; spec 002 is the source of truth.
const ID_PATTERN = /^[a-z0-9]+(-[a-z0-9]+)*(\/[a-z0-9]+(-[a-z0-9]+)*)?$/; // section ids
const SLUG_PATTERN = /^[a-z0-9]+(-[a-z0-9]+)*$/; // move and class ids
const DAMAGE_PATTERN = /^d\d+$/;

function nonEmptyAfterTrim(value: string): boolean {
  return value.trim().length > 0;
}

const StatSchema = z.enum([
  "STR",
  "DEX",
  "CON",
  "INT",
  "WIS",
  "CHA",
  "BOND",
  "VARIES",
  "NONE",
]);

export type Stat = z.infer<typeof StatSchema>;

const SectionSchema = z
  .object({
    id: z.string().regex(ID_PATTERN),
    chapter: z.string(),
    title: z.string().refine(nonEmptyAfterTrim, "must be non-empty"),
    slug: z.string(),
    parent_id: z.string().nullable(),
    order: z.number().int(),
    text_markdown: z.string(),
  })
  .strict();

export type Section = z.infer<typeof SectionSchema>;

const OutcomesSchema = z
  .object({
    strong_hit: z.string(),
    weak_hit: z.string(),
    miss: z.string().nullable(),
  })
  .strict();

export type Outcomes = z.infer<typeof OutcomesSchema>;

const MoveSchema = z
  .object({
    id: z.string().regex(SLUG_PATTERN),
    name: z.string().refine(nonEmptyAfterTrim, "must be non-empty"),
    category: z.enum(["basic", "special", "class"]),
    class: z.string().nullable(),
    stat: StatSchema.nullable(),
    trigger: z.string().refine(nonEmptyAfterTrim, "must be non-empty"),
    outcomes: OutcomesSchema.nullable(),
    body_markdown: z.string(),
    section_id: z.string(),
  })
  .strict();

export type Move = z.infer<typeof MoveSchema>;

const GameClassSchema = z
  .object({
    id: z.string().regex(SLUG_PATTERN),
    name: z.string(),
    section_id: z.string(),
    order: z.number().int(),
    max_hp_base: z.number().int().positive(),
    base_damage: z.string().regex(DAMAGE_PATTERN),
    load_base: z.number().int().positive(),
  })
  .strict();

export type GameClass = z.infer<typeof GameClassSchema>;

const SectionArraySchema = z.array(SectionSchema);
const MoveArraySchema = z.array(MoveSchema);
const GameClassArraySchema = z.array(GameClassSchema);

export interface Rulebook {
  sections: readonly Section[];
  moves: readonly Move[];
  classes: readonly GameClass[];
  sectionById: ReadonlyMap<string, Section>;
  moveById: ReadonlyMap<string, Move>;
  moveBySectionId: ReadonlyMap<string, Move>;
  classBySectionId: ReadonlyMap<string, GameClass>;
  childrenOf: ReadonlyMap<string, readonly Section[]>;
}

export class RulebookError extends Error {}

function getAtPath(obj: unknown, path: readonly PropertyKey[]): unknown {
  let current: unknown = obj;
  for (const key of path) {
    if (current === null || typeof current !== "object") return undefined;
    current = (current as Record<PropertyKey, unknown>)[key];
  }
  return current;
}

function formatIssues(label: string, rawArray: unknown, error: z.ZodError): string[] {
  return error.issues.map((issue) => {
    const pathStr = issue.path.length > 0 ? issue.path.join(".") : "(root)";
    const value = getAtPath(rawArray, issue.path);
    const suffix = value !== undefined ? ` (received ${JSON.stringify(value)})` : "";
    return `${label}[${pathStr}]: ${issue.message}${suffix}`;
  });
}

export function parseRulebook(raw: {
  sections: unknown;
  moves: unknown;
  classes: unknown;
}): Rulebook {
  const sectionsResult = SectionArraySchema.safeParse(raw.sections);
  const movesResult = MoveArraySchema.safeParse(raw.moves);
  const classesResult = GameClassArraySchema.safeParse(raw.classes);

  const problems: string[] = [];
  if (!sectionsResult.success) {
    problems.push(...formatIssues("sections", raw.sections, sectionsResult.error));
  }
  if (!movesResult.success) {
    problems.push(...formatIssues("moves", raw.moves, movesResult.error));
  }
  if (!classesResult.success) {
    problems.push(...formatIssues("classes", raw.classes, classesResult.error));
  }

  const sections = sectionsResult.success ? sectionsResult.data : undefined;
  const moves = movesResult.success ? movesResult.data : undefined;
  const classes = classesResult.success ? classesResult.data : undefined;

  if (sections) {
    const idCounts = new Map<string, number>();
    const orderCounts = new Map<number, number>();
    for (const section of sections) {
      idCounts.set(section.id, (idCounts.get(section.id) ?? 0) + 1);
      orderCounts.set(section.order, (orderCounts.get(section.order) ?? 0) + 1);
    }
    for (const [id, count] of idCounts) {
      if (count > 1) problems.push(`sections: duplicate id "${id}"`);
    }
    for (const [order, count] of orderCounts) {
      if (count > 1) problems.push(`sections: duplicate order ${order}`);
    }
    const sectionIds = new Set(sections.map((section) => section.id));
    for (const section of sections) {
      if (section.parent_id !== null && !sectionIds.has(section.parent_id)) {
        problems.push(
          `sections: section "${section.id}" has dangling parent_id "${section.parent_id}"`,
        );
      }
    }
  }

  if (moves) {
    const idCounts = new Map<string, number>();
    for (const move of moves) {
      idCounts.set(move.id, (idCounts.get(move.id) ?? 0) + 1);
    }
    for (const [id, count] of idCounts) {
      if (count > 1) problems.push(`moves: duplicate id "${id}"`);
    }
    if (sections) {
      const sectionIds = new Set(sections.map((section) => section.id));
      for (const move of moves) {
        if (!sectionIds.has(move.section_id)) {
          problems.push(
            `moves: move "${move.id}" has section_id "${move.section_id}" which does not exist`,
          );
        }
      }
    }
  }

  if (classes) {
    const idCounts = new Map<string, number>();
    for (const gameClass of classes) {
      idCounts.set(gameClass.id, (idCounts.get(gameClass.id) ?? 0) + 1);
    }
    for (const [id, count] of idCounts) {
      if (count > 1) problems.push(`classes: duplicate id "${id}"`);
    }
    if (sections) {
      const sectionIds = new Set(sections.map((section) => section.id));
      for (const gameClass of classes) {
        if (!sectionIds.has(gameClass.section_id)) {
          problems.push(
            `classes: class "${gameClass.id}" has section_id "${gameClass.section_id}" which does not exist`,
          );
        }
      }
    }
  }

  if (problems.length > 0) {
    throw new RulebookError(problems.join("\n"));
  }
  if (!sections || !moves || !classes) {
    // Unreachable: no problems were collected, so every array shape-parsed successfully.
    throw new RulebookError("rulebook: unexpected internal validation failure");
  }

  const sortedSections = [...sections].sort((a, b) => a.order - b.order);
  const sortedClasses = [...classes].sort((a, b) => a.order - b.order);

  const sectionById = new Map(sortedSections.map((section) => [section.id, section]));
  const moveById = new Map(moves.map((move) => [move.id, move]));
  const moveBySectionId = new Map(moves.map((move) => [move.section_id, move]));
  const classBySectionId = new Map(classes.map((gameClass) => [gameClass.section_id, gameClass]));

  const childrenOf = new Map<string, Section[]>();
  for (const section of sortedSections) {
    childrenOf.set(section.id, []);
  }
  for (const section of sortedSections) {
    if (section.parent_id !== null) {
      childrenOf.get(section.parent_id)?.push(section);
    }
  }

  return {
    sections: sortedSections,
    moves,
    classes: sortedClasses,
    sectionById,
    moveById,
    moveBySectionId,
    classBySectionId,
    childrenOf,
  };
}

let memoised: Rulebook | undefined;

export function loadRulebook(): Rulebook {
  if (!memoised) {
    memoised = parseRulebook({
      sections: JSON.parse(sectionsRaw),
      moves: JSON.parse(movesRaw),
      classes: JSON.parse(classesRaw),
    });
  }
  return memoised;
}

export function ancestorsOf(rb: Rulebook, id: string): readonly Section[] {
  const ancestors: Section[] = [];
  let current = rb.sectionById.get(id);
  while (current && current.parent_id !== null) {
    const parent = rb.sectionById.get(current.parent_id);
    if (!parent) break;
    ancestors.unshift(parent);
    current = parent;
  }
  return ancestors;
}
