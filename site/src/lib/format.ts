import type { Stat } from "./rulebook";

const SITE_NAME = "Dungeon World Companion";

const ROLL_LABELS: Record<Stat, string> = {
  STR: "+STR",
  DEX: "+DEX",
  CON: "+CON",
  INT: "+INT",
  WIS: "+WIS",
  CHA: "+CHA",
  BOND: "+Bond",
  VARIES: "+stat chosen by how you act",
  NONE: "2d6, no stat added",
};

export function rollLabel(stat: Stat | null): string {
  if (stat === null) return "Not rolled";
  return ROLL_LABELS[stat];
}

const CATEGORY_LABELS: Record<"basic" | "special" | "class", string> = {
  basic: "Basic move",
  special: "Special move",
  class: "Class move",
};

export function categoryLabel(category: "basic" | "special" | "class"): string {
  return CATEGORY_LABELS[category];
}

export function pageTitle(title?: string): string {
  if (title === undefined) return `${SITE_NAME} (unofficial)`;
  return `${title} · ${SITE_NAME}`;
}
