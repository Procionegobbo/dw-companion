// Wire contract for the chat API (spec 008 "Frontend types"). Schemas are intentionally
// non-strict: unknown keys are stripped rather than rejected, so the server can add fields
// without breaking the widget (D1). Every citation/move `url` is checked against the same
// `sectionUrl`/`moveUrl` builders the rest of the site uses (D16) — a payload cannot carry an
// arbitrary href, only one that matches the id it claims to point at.

import { z } from "zod";
import { moveUrl, sectionUrl } from "../urls";
import type { Stat } from "../rulebook";

export type ReplyKind =
  | "rules_answer"
  | "rules_not_found"
  | "move"
  | "no_move"
  | "clarification"
  | "out_of_scope"
  | "error";

export type Band = "strong_hit" | "weak_hit" | "miss";

export type AbilityStat = "STR" | "DEX" | "CON" | "INT" | "WIS" | "CHA";

export interface Citation {
  section_id: string;
  title: string;
  url: string; // url === sectionUrl(section_id)
}

export interface MoveCardPayload {
  move_id: string;
  name: string;
  url: string; // url === moveUrl(move_id)
  trigger: string;
  stat: Stat | null;
  roll_stat: AbilityStat | null;
  outcomes: { strong_hit: string; weak_hit: string; miss: string | null } | null;
  roll: { dice: [number, number]; modifier: number | null; total: number | null } | null;
  outcome: { band: Band; text: string | null } | null;
  bands_by_modifier: { modifier: number; band: Band }[];
}

export interface ChatReply {
  trace_id: string;
  kind: ReplyKind;
  text: string;
  citations: Citation[];
  move: MoveCardPayload | null;
}

function urlMatches(expected: (id: string) => string, id: string, url: string): boolean {
  try {
    return expected(id) === url;
  } catch {
    return false;
  }
}

const replyKindSchema = z.enum([
  "rules_answer",
  "rules_not_found",
  "move",
  "no_move",
  "clarification",
  "out_of_scope",
  "error",
]);

const bandSchema = z.enum(["strong_hit", "weak_hit", "miss"]);

const statSchema = z.enum(["STR", "DEX", "CON", "INT", "WIS", "CHA", "BOND", "VARIES", "NONE"]);

const abilityStatSchema = z.enum(["STR", "DEX", "CON", "INT", "WIS", "CHA"]);

const citationSchema = z
  .object({
    section_id: z.string(),
    title: z.string(),
    url: z.string(),
  })
  .refine((citation) => urlMatches(sectionUrl, citation.section_id, citation.url), {
    message: "citation url must equal sectionUrl(section_id)",
  });

const diceFaceSchema = z.number().int().min(1).max(6);

const moveOutcomesSchema = z.object({
  strong_hit: z.string(),
  weak_hit: z.string(),
  miss: z.string().nullable(),
});

const moveRollSchema = z.object({
  dice: z.tuple([diceFaceSchema, diceFaceSchema]),
  modifier: z.number().int().nullable(),
  total: z.number().int().nullable(),
});

const moveOutcomeSchema = z.object({
  band: bandSchema,
  text: z.string().nullable(),
});

const bandByModifierSchema = z.object({
  modifier: z.number().int(),
  band: bandSchema,
});

const moveCardSchema = z
  .object({
    move_id: z.string(),
    name: z.string(),
    url: z.string(),
    trigger: z.string(),
    stat: statSchema.nullable(),
    roll_stat: abilityStatSchema.nullable(),
    outcomes: moveOutcomesSchema.nullable(),
    roll: moveRollSchema.nullable(),
    outcome: moveOutcomeSchema.nullable(),
    bands_by_modifier: z.array(bandByModifierSchema),
  })
  .refine((move) => urlMatches(moveUrl, move.move_id, move.url), {
    message: "move url must equal moveUrl(move_id)",
  });

export const replySchema: z.ZodType<ChatReply> = z.object({
  trace_id: z.string(),
  kind: replyKindSchema,
  text: z.string(),
  citations: z.array(citationSchema),
  move: moveCardSchema.nullable(),
});

export const statusSchema = z.object({
  step: z.string(),
});

export const streamErrorSchema = z.object({
  code: z.string(),
  message: z.string(),
});

export const httpErrorSchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
  }),
});
