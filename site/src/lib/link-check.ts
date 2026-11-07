// Verifies the built output of `npm run build`: every section and move id resolves to a page
// carrying its id marker, every internal link on every page resolves, and every page carries
// the attribution footer. Pure Node `fs`/`path` — no HTTP server, no network request. Spec 004
// *Link Check*.

import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import type { Rulebook } from "./rulebook";

export interface LinkCheckReport {
  pages: number;
  internalLinks: number;
  problems: readonly string[];
}

const HREF_PATTERN = /href="([^"]*)"/g;

const FOOTER_MARKERS = [
  "https://creativecommons.org/licenses/by/3.0/",
  "https://github.com/Sagelt/Dungeon-World",
  "unofficial",
];

function listHtmlFiles(dir: string): string[] {
  const files: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...listHtmlFiles(full));
    } else if (entry.isFile() && entry.name.endsWith(".html")) {
      files.push(full);
    }
  }
  return files;
}

function decodeAmp(value: string): string {
  return value.replace(/&amp;/g, "&");
}

/** Splits a raw href into its path and (if present) fragment, stripping any query string. */
function splitHref(href: string): { path: string; fragment: string | undefined } {
  const decoded = decodeAmp(href);
  const hashIndex = decoded.indexOf("#");
  const beforeFragment = hashIndex === -1 ? decoded : decoded.slice(0, hashIndex);
  const fragment = hashIndex === -1 ? undefined : decoded.slice(hashIndex + 1);
  const queryIndex = beforeFragment.indexOf("?");
  const path = queryIndex === -1 ? beforeFragment : beforeFragment.slice(0, queryIndex);
  return { path, fragment };
}

function hasId(html: string, id: string): boolean {
  return html.includes(`id="${id}"`);
}

function checkIdCoverage(distDir: string, rb: Rulebook, problems: string[]): void {
  for (const section of rb.sections) {
    const file = join(distDir, "rules", section.id, "index.html");
    if (!existsSync(file)) {
      problems.push(`missing section page for id "${section.id}": expected ${file}`);
      continue;
    }
    const html = readFileSync(file, "utf-8");
    if (!html.includes(`data-section-id="${section.id}"`)) {
      problems.push(`${file}: missing data-section-id="${section.id}" marker`);
    }
  }

  for (const move of rb.moves) {
    const file = join(distDir, "moves", move.id, "index.html");
    if (!existsSync(file)) {
      problems.push(`missing move page for id "${move.id}": expected ${file}`);
      continue;
    }
    const html = readFileSync(file, "utf-8");
    if (!html.includes(`data-move-id="${move.id}"`)) {
      problems.push(`${file}: missing data-move-id="${move.id}" marker`);
    }
  }

  for (const requiredPath of ["index.html", join("moves", "index.html"), "404.html"]) {
    const file = join(distDir, requiredPath);
    if (!existsSync(file)) {
      problems.push(`missing required page: expected ${file}`);
    }
  }
}

function checkFooter(file: string, html: string, problems: string[]): void {
  for (const marker of FOOTER_MARKERS) {
    if (!html.includes(marker)) {
      problems.push(`${file}: missing attribution footer (no "${marker}")`);
    }
  }
}

/** Resolves a root-relative href's path to the dist file it points at. Returns the file path,
 * or undefined with a problem already pushed when it can't be resolved. */
function resolveInternalTarget(
  distDir: string,
  file: string,
  href: string,
  path: string,
  problems: string[],
): string | undefined {
  if (path.endsWith("/")) {
    const target = join(distDir, path, "index.html");
    if (!existsSync(target)) {
      problems.push(`${file}: broken link "${href}" (no ${target})`);
      return undefined;
    }
    return target;
  }

  const directTarget = join(distDir, path);
  if (existsSync(directTarget) && statSync(directTarget).isFile()) {
    return directTarget;
  }

  const indexTarget = join(distDir, path, "index.html");
  if (existsSync(indexTarget)) {
    problems.push(`${file}: link "${href}" is missing its trailing slash`);
    return undefined;
  }

  problems.push(`${file}: broken link "${href}" (no ${directTarget})`);
  return undefined;
}

function checkInternalLinks(
  distDir: string,
  file: string,
  html: string,
  problems: string[],
): number {
  let count = 0;
  for (const match of html.matchAll(HREF_PATTERN)) {
    const href = match[1] ?? "";

    if (/^(https?:|mailto:)/.test(href)) {
      continue; // external, never fetched
    }

    if (href.startsWith("#")) {
      count++;
      const fragment = href.slice(1);
      if (!hasId(html, fragment)) {
        problems.push(`${file}: broken fragment "${href}" (no id="${fragment}" in this page)`);
      }
      continue;
    }

    if (href.startsWith("/") && !href.startsWith("//")) {
      count++;
      const { path, fragment } = splitHref(href);
      const target = resolveInternalTarget(distDir, file, href, path, problems);
      if (target && fragment !== undefined) {
        const targetHtml = readFileSync(target, "utf-8");
        if (!hasId(targetHtml, fragment)) {
          problems.push(
            `${file}: broken fragment "${href}" (no id="${fragment}" in ${target})`,
          );
        }
      }
      continue;
    }

    problems.push(`${file}: non-root-relative link "${href}"`);
  }
  return count;
}

export function checkSite(distDir: string, rb: Rulebook): LinkCheckReport {
  const problems: string[] = [];

  checkIdCoverage(distDir, rb, problems);

  const htmlFiles = existsSync(distDir) ? listHtmlFiles(distDir) : [];
  let internalLinks = 0;

  for (const file of htmlFiles) {
    const html = readFileSync(file, "utf-8");
    checkFooter(file, html, problems);
    internalLinks += checkInternalLinks(distDir, file, html, problems);
  }

  return { pages: htmlFiles.length, internalLinks, problems };
}
