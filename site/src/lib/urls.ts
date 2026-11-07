// The only place URLs are built from ids (the citation contract — spec 004 D1). Every page and
// component must import from here rather than building a "/rules/" or "/moves/" path itself.

// Mirrors the id patterns validated in rulebook.ts; kept local so urls.ts has no dependency on
// loading the committed rulebook data.
const SECTION_ID_PATTERN = /^[a-z0-9]+(-[a-z0-9]+)*(\/[a-z0-9]+(-[a-z0-9]+)*)?$/;
const MOVE_ID_PATTERN = /^[a-z0-9]+(-[a-z0-9]+)*$/;

export const HOME_URL = "/";
export const MOVES_INDEX_URL = "/moves/";

export function sectionUrl(sectionId: string): string {
  if (!SECTION_ID_PATTERN.test(sectionId)) {
    throw new Error(`invalid section id: "${sectionId}"`);
  }
  return `/rules/${sectionId}/`;
}

export function moveUrl(moveId: string): string {
  if (!MOVE_ID_PATTERN.test(moveId)) {
    throw new Error(`invalid move id: "${moveId}"`);
  }
  return `/moves/${moveId}/`;
}
