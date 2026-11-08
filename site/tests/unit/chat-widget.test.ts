// @vitest-environment happy-dom
import { readFileSync } from "node:fs";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { mountChatWidget } from "../../src/lib/chat/widget";
import type { ChatOutcome, ChatRequestBody } from "../../src/lib/chat/client";
import type { ChatReply } from "../../src/lib/chat/protocol";

// `import.meta.url` is assigned to a variable before being passed to `new URL` because Vite's
// static asset-URL analysis rewrites the inline pattern `new URL("...", import.meta.url)` under
// the happy-dom test environment, producing an http: URL instead of the real file: one.
const moduleUrl = import.meta.url;
const fixture = JSON.parse(
  readFileSync(
    new URL("../../../backend/tests/fixtures/chat_reply_examples.json", moduleUrl),
  ).toString(),
) as { rules_answer: ChatReply };

const SESSION_ID = "ab".repeat(16);

// Markup matching `ChatWidget.astro`'s rendered ids exactly (spec 008 "Page and component").
const MARKUP = `
  <section id="chat" class="chat" aria-labelledby="chat-heading">
    <h2 id="chat-heading" class="visually-hidden">Conversation</h2>
    <ol id="chat-log" class="chat-log" role="log" aria-label="Conversation"></ol>
    <p id="chat-status" class="chat-status" role="status"></p>
    <form id="chat-form" novalidate>
      <label for="chat-message">Your message</label>
      <textarea id="chat-message" name="message" rows="3" maxlength="500" required
        aria-describedby="chat-count chat-message-error"></textarea>
      <p id="chat-count" class="chat-count">0/500</p>
      <p id="chat-message-error" class="chat-field-error" hidden></p>
      <label><input type="checkbox" id="chat-roll" name="roll" /> Roll the dice for me</label>
      <label for="chat-modifier">Modifier (optional)</label>
      <input type="number" id="chat-modifier" name="modifier" min="-10" max="10" step="1"
        inputmode="numeric" disabled aria-describedby="chat-modifier-error" />
      <p id="chat-modifier-error" class="chat-field-error" hidden></p>
      <button type="submit" id="chat-submit">Ask</button>
    </form>
  </section>
`;

function required<T>(value: T | null): T {
  if (value === null) throw new Error("expected element to exist");
  return value;
}

function elements() {
  return {
    log: required(document.querySelector<HTMLOListElement>("#chat-log")),
    status: required(document.querySelector<HTMLParagraphElement>("#chat-status")),
    form: required(document.querySelector<HTMLFormElement>("#chat-form")),
    textarea: required(document.querySelector<HTMLTextAreaElement>("#chat-message")),
    counter: required(document.querySelector<HTMLParagraphElement>("#chat-count")),
    messageError: required(document.querySelector<HTMLParagraphElement>("#chat-message-error")),
    rollCheckbox: required(document.querySelector<HTMLInputElement>("#chat-roll")),
    modifierInput: required(document.querySelector<HTMLInputElement>("#chat-modifier")),
    modifierError: required(document.querySelector<HTMLParagraphElement>("#chat-modifier-error")),
    submitButton: required(document.querySelector<HTMLButtonElement>("#chat-submit")),
  };
}

type SendFn = (
  body: ChatRequestBody,
  opts?: { onStatus?: (step: string) => void },
) => Promise<ChatOutcome>;

function okSend(reply: ChatReply) {
  return vi.fn<SendFn>(async () => ({ type: "reply", reply }));
}

function failSend(code: string, message: string) {
  return vi.fn<SendFn>(async () => ({ type: "failure", code, message }));
}

function submitViaButton(form: HTMLFormElement): void {
  form.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
}

async function flush(): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

interface DeferredSend {
  send: (body: ChatRequestBody, opts?: { onStatus?: (step: string) => void }) => Promise<ChatOutcome>;
  resolve: (outcome: ChatOutcome) => void;
  calls: ChatRequestBody[];
  opts: { onStatus?: (step: string) => void } | undefined;
}

function deferredSend(): DeferredSend {
  let resolve!: (outcome: ChatOutcome) => void;
  const promise = new Promise<ChatOutcome>((r) => {
    resolve = r;
  });
  const result: DeferredSend = {
    calls: [],
    opts: undefined,
    resolve: (outcome) => resolve(outcome),
    send: (body, opts) => {
      result.calls.push(body);
      result.opts = opts;
      return promise;
    },
  };
  return result;
}

beforeEach(() => {
  document.body.innerHTML = MARKUP;
});

describe("mountChatWidget", () => {
  it("sends the trimmed message with session id", async () => {
    const send = okSend(fixture.rules_answer);
    mountChatWidget({ send, newSessionId: () => SESSION_ID });
    const { textarea, form, log } = elements();

    textarea.value = "  hi  ";
    submitViaButton(form);
    await flush();

    expect(send).toHaveBeenCalledTimes(1);
    expect(send.mock.calls[0]?.[0]).toEqual({
      message: "hi",
      roll: false,
      modifier: null,
      session_id: SESSION_ID,
    });
    expect(log.children).toHaveLength(2);
    expect(log.children[0]?.className).toBe("chat-user");
  });

  it("blocks an empty message", async () => {
    const send = vi.fn();
    mountChatWidget({ send, newSessionId: () => SESSION_ID });
    const { textarea, form, messageError } = elements();

    textarea.value = "   ";
    submitViaButton(form);
    await flush();

    expect(send).not.toHaveBeenCalled();
    expect(messageError.hidden).toBe(false);
    expect(messageError.textContent).toBe("Type a message first.");
  });

  it("modifier enabled only when roll is checked", () => {
    mountChatWidget({ send: vi.fn(), newSessionId: () => SESSION_ID });
    const { rollCheckbox, modifierInput } = elements();

    expect(modifierInput.disabled).toBe(true);

    rollCheckbox.checked = true;
    rollCheckbox.dispatchEvent(new Event("change"));
    expect(modifierInput.disabled).toBe(false);

    rollCheckbox.checked = false;
    rollCheckbox.dispatchEvent(new Event("change"));
    expect(modifierInput.disabled).toBe(true);
  });

  it("sends the modifier only when rolling", async () => {
    const send = okSend(fixture.rules_answer);
    mountChatWidget({ send, newSessionId: () => SESSION_ID });
    const { textarea, form, rollCheckbox, modifierInput } = elements();

    rollCheckbox.checked = true;
    rollCheckbox.dispatchEvent(new Event("change"));
    modifierInput.value = "-2";
    textarea.value = "hi";
    submitViaButton(form);
    await flush();
    expect(send.mock.calls[0]?.[0]?.modifier).toBe(-2);

    rollCheckbox.checked = false;
    rollCheckbox.dispatchEvent(new Event("change"));
    textarea.value = "hi again";
    submitViaButton(form);
    await flush();
    expect(send.mock.calls[1]?.[0]?.modifier).toBeNull();
  });

  it("rejects an invalid modifier", async () => {
    const send = vi.fn();
    mountChatWidget({ send, newSessionId: () => SESSION_ID });
    const { textarea, form, rollCheckbox, modifierInput, modifierError } = elements();

    rollCheckbox.checked = true;
    rollCheckbox.dispatchEvent(new Event("change"));
    modifierInput.value = "11";
    textarea.value = "hi";
    submitViaButton(form);
    await flush();

    expect(send).not.toHaveBeenCalled();
    expect(modifierError.hidden).toBe(false);
    expect(modifierError.textContent).toBe("Enter a whole number from -10 to 10, or leave it empty.");
  });

  it("shows progress and disables the button while pending", async () => {
    const deferred = deferredSend();
    mountChatWidget({ send: deferred.send, newSessionId: () => SESSION_ID });
    const { textarea, form, status, submitButton, log } = elements();

    textarea.value = "hi";
    submitViaButton(form);
    await flush();

    expect(submitButton.disabled).toBe(true);
    expect(submitButton.textContent).toBe("Asking…");
    expect(status.textContent).toBe("Reading your message…");

    deferred.opts?.onStatus?.("retrieve");
    expect(status.textContent).toBe("Writing an answer from the rules…");

    deferred.opts?.onStatus?.("citation_validator");
    expect(status.textContent).toBe("Writing an answer from the rules…");

    deferred.resolve({ type: "reply", reply: fixture.rules_answer });
    await flush();

    expect(status.textContent).toBe("");
    expect(submitButton.disabled).toBe(false);
    expect(submitButton.textContent).toBe("Ask");
    expect(log.children).toHaveLength(2);
  });

  it("ignores a second submit while pending", async () => {
    const { send } = deferredSend();
    const sendSpy = vi.fn(send);
    mountChatWidget({ send: sendSpy, newSessionId: () => SESSION_ID });
    const { textarea, form } = elements();

    textarea.value = "hi";
    submitViaButton(form);
    await flush();

    textarea.value = "another";
    submitViaButton(form);
    await flush();

    expect(sendSpy).toHaveBeenCalledTimes(1);
  });

  it("renders a failure and restores the message", async () => {
    const send = failSend("internal_error", "Something broke.");
    mountChatWidget({ send, newSessionId: () => SESSION_ID });
    const { textarea, form, log } = elements();

    textarea.value = "hi";
    submitViaButton(form);
    await flush();

    const errorItem = log.querySelector(".chat-error");
    expect(errorItem).not.toBeNull();
    expect(textarea.value).toBe("hi");
  });

  it("enter submits and shift enter does not", async () => {
    const send = okSend(fixture.rules_answer);
    mountChatWidget({ send, newSessionId: () => SESSION_ID });
    const { textarea } = elements();

    textarea.value = "hi";
    textarea.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Enter", shiftKey: false, cancelable: true }),
    );
    await flush();
    expect(send).toHaveBeenCalledTimes(1);

    textarea.value = "hi again";
    textarea.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Enter", shiftKey: true, cancelable: true }),
    );
    await flush();
    expect(send).toHaveBeenCalledTimes(1);
  });

  it("updates the character counter", () => {
    mountChatWidget({ send: vi.fn(), newSessionId: () => SESSION_ID });
    const { textarea, counter } = elements();

    textarea.value = "hello";
    textarea.dispatchEvent(new Event("input"));
    expect(counter.textContent).toBe("5/500");
  });

  it("uses a fresh session id per mount only", async () => {
    const send = okSend(fixture.rules_answer);
    mountChatWidget({ send, newSessionId: () => SESSION_ID });
    const { textarea, form } = elements();

    textarea.value = "first";
    submitViaButton(form);
    await flush();

    textarea.value = "second";
    submitViaButton(form);
    await flush();

    expect(send.mock.calls[0]?.[0]?.session_id).toBe(SESSION_ID);
    expect(send.mock.calls[1]?.[0]?.session_id).toBe(SESSION_ID);
  });
});
