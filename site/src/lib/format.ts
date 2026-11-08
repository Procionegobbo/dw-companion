import type { Stat } from "./rulebook";
import type { Band } from "./chat/protocol";

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

const BAND_LABELS: Record<Band, string> = {
  strong_hit: "10+ (strong hit)",
  weak_hit: "7–9 (weak hit)",
  miss: "6- (miss)",
};

export function bandLabel(band: Band): string {
  return BAND_LABELS[band];
}
