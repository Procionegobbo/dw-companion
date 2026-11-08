// Turns a validated ChatReply into DOM nodes (spec 008 D16: render safety). Every piece of
// server-authored text is placed with `textContent`/`createTextNode` only — raw HTML is never
// parsed from the payload — and every `href` is the schema-checked `citation.url`/`move.url`
// already validated by protocol.ts against urls.ts's own builders.

import type { Band, ChatReply, Citation, MoveCardPayload } from "./protocol";
import { bandLabel, rollLabel } from "../format";
import { CLOSEST_TITLE, NEW_TAB, NOT_STATED, SOURCES_TITLE, YOUR_ROLL } from "./copy";

export type Segment =
  | { type: "text"; text: string }
  | { type: "citation"; index: number; citation: Citation };

const MARKER_PATTERN = /\[\[([^[\]\s]+)\]\]/g;

/** Splits `text` on `[[section_id]]` markers, replacing each known one with its 1-based
 * citation index. Markers that are not in `citations` are dropped entirely (spec 008 D16). */
export function segmentText(text: string, citations: readonly Citation[]): Segment[] {
  const bySectionId = new Map(
    citations.map((citation, i) => [citation.section_id, { citation, index: i + 1 }]),
  );
  const segments: Segment[] = [];
  let lastIndex = 0;

  for (const match of text.matchAll(MARKER_PATTERN)) {
    const start = match.index;
    const end = start + match[0].length;
    const before = text.slice(lastIndex, start);
    if (before) segments.push({ type: "text", text: before });

    const found = bySectionId.get(match[1] ?? "");
    if (found) {
      segments.push({ type: "citation", index: found.index, citation: found.citation });
    }
    lastIndex = end;
  }

  const tail = text.slice(lastIndex);
  if (tail) segments.push({ type: "text", text: tail });
  return segments;
}

/** Formats a move's rolled dice, e.g. "4 + 5 + 1 = 10" or "3 + 5 = 8, before your modifier". */
export function diceText(roll: NonNullable<MoveCardPayload["roll"]>): string {
  const [d1, d2] = roll.dice;
  if (roll.modifier === null) {
    return `${d1} + ${d2} = ${d1 + d2}, before your modifier`;
  }
  const sign = roll.modifier < 0 ? "-" : "+";
  const total = roll.total ?? d1 + d2 + roll.modifier;
  return `${d1} + ${d2} ${sign} ${Math.abs(roll.modifier)} = ${total}`;
}

function newTabLink(doc: Document, href: string, label: string): HTMLAnchorElement {
  const a = doc.createElement("a");
  a.href = href;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  a.appendChild(doc.createTextNode(label));
  const hidden = doc.createElement("span");
  hidden.className = "visually-hidden";
  hidden.textContent = NEW_TAB;
  a.appendChild(hidden);
  return a;
}

function visuallyHiddenPrefix(doc: Document, text: string): HTMLSpanElement {
  const span = doc.createElement("span");
  span.className = "visually-hidden";
  span.textContent = text;
  return span;
}

export function renderUserMessage(doc: Document, text: string): HTMLLIElement {
  const li = doc.createElement("li");
  li.className = "chat-user";
  li.appendChild(visuallyHiddenPrefix(doc, "You: "));
  li.appendChild(doc.createTextNode(text));
  return li;
}

export function renderFailure(doc: Document, message: string): HTMLLIElement {
  const li = doc.createElement("li");
  li.className = "chat-assistant chat-error";
  li.dataset.kind = "failure";
  li.appendChild(visuallyHiddenPrefix(doc, "Assistant: "));

  const p = doc.createElement("p");
  const strong = doc.createElement("strong");
  strong.textContent = "Error: ";
  p.appendChild(strong);
  p.appendChild(doc.createTextNode(message));
  li.appendChild(p);
  return li;
}

function appendFact(doc: Document, dl: HTMLDListElement, label: string, value: string): void {
  const dt = doc.createElement("dt");
  dt.textContent = label;
  const dd = doc.createElement("dd");
  dd.textContent = value;
  dl.appendChild(dt);
  dl.appendChild(dd);
}

const OUTCOME_BANDS: readonly Band[] = ["strong_hit", "weak_hit", "miss"];

function outcomeText(outcomes: NonNullable<MoveCardPayload["outcomes"]>, band: Band): string {
  if (band === "miss") return outcomes.miss ?? NOT_STATED;
  return outcomes[band];
}

function renderMoveCard(doc: Document, move: MoveCardPayload): HTMLElement {
  const section = doc.createElement("section");
  section.className = "move-card";
  section.setAttribute("aria-label", `Move: ${move.name}`);

  const h3 = doc.createElement("h3");
  h3.appendChild(newTabLink(doc, move.url, move.name));
  section.appendChild(h3);

  const facts = doc.createElement("dl");
  facts.className = "move-facts";
  appendFact(doc, facts, "Trigger", move.trigger);
  appendFact(doc, facts, "Roll", rollLabel(move.roll_stat ?? move.stat));
  if (move.roll) {
    appendFact(doc, facts, "Dice", diceText(move.roll));
  }
  section.appendChild(facts);

  if (move.outcomes) {
    const outcomesDl = doc.createElement("dl");
    outcomesDl.className = "outcomes";
    for (const band of OUTCOME_BANDS) {
      const isResult = move.outcome?.band === band;
      const dt = doc.createElement("dt");
      dt.textContent = bandLabel(band) + (isResult ? YOUR_ROLL : "");
      const dd = doc.createElement("dd");
      dd.textContent = outcomeText(move.outcomes, band);
      if (isResult) {
        dt.classList.add("is-result");
        dd.classList.add("is-result");
      }
      outcomesDl.appendChild(dt);
      outcomesDl.appendChild(dd);
    }
    section.appendChild(outcomesDl);
  }

  return section;
}

export function renderReply(doc: Document, reply: ChatReply): HTMLLIElement {
  const li = doc.createElement("li");
  li.className = "chat-assistant";
  li.dataset.kind = reply.kind;
  if (reply.kind === "error") li.classList.add("chat-error");
  li.appendChild(visuallyHiddenPrefix(doc, "Assistant: "));

  const textDiv = doc.createElement("div");
  textDiv.className = "chat-text";
  const paragraphs = reply.text.split(/\n{2,}/);
  paragraphs.forEach((paragraphText, index) => {
    const p = doc.createElement("p");
    if (reply.kind === "error" && index === 0) {
      const strong = doc.createElement("strong");
      strong.textContent = "Error: ";
      p.appendChild(strong);
    }
    for (const segment of segmentText(paragraphText, reply.citations)) {
      if (segment.type === "text") {
        p.appendChild(doc.createTextNode(segment.text));
        continue;
      }
      const a = doc.createElement("a");
      a.href = segment.citation.url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.setAttribute(
        "aria-label",
        `Source ${segment.index}: ${segment.citation.title}${NEW_TAB}`,
      );
      a.textContent = `[${segment.index}]`;
      p.appendChild(a);
    }
    textDiv.appendChild(p);
  });
  li.appendChild(textDiv);

  if (reply.citations.length > 0) {
    const title = doc.createElement("p");
    title.className = "chat-sources-title";
    title.textContent = reply.kind === "rules_not_found" ? CLOSEST_TITLE : SOURCES_TITLE;
    li.appendChild(title);

    const ol = doc.createElement("ol");
    ol.className = "chat-sources";
    for (const citation of reply.citations) {
      const item = doc.createElement("li");
      item.appendChild(newTabLink(doc, citation.url, citation.title));
      ol.appendChild(item);
    }
    li.appendChild(ol);
  }

  if (reply.move) {
    li.appendChild(renderMoveCard(doc, reply.move));
  }

  return li;
}
