// Mounts the chat widget behaviour onto `ChatWidget.astro`'s markup (spec 008 "widget.ts").
// Pure DOM wiring: validation, progress copy and rendering are delegated to `client.ts`,
// `copy.ts` and `render.ts` respectively. `innerHTML` is never assigned here.

import { MAX_MESSAGE_CHARS, sendChat, type ChatRequestBody } from "./client";
import { EMPTY_MESSAGE, MODIFIER_INVALID, STATUS_BY_STEP, STATUS_START } from "./copy";
import { renderFailure, renderReply, renderUserMessage } from "./render";

function resolveDocument(root: ParentNode): Document {
  if (root instanceof Document) return root;
  return (root as unknown as Node).ownerDocument ?? document;
}

interface WidgetElements {
  log: HTMLOListElement;
  status: HTMLParagraphElement;
  form: HTMLFormElement;
  textarea: HTMLTextAreaElement;
  counter: HTMLParagraphElement;
  messageError: HTMLParagraphElement;
  rollCheckbox: HTMLInputElement;
  modifierInput: HTMLInputElement;
  modifierError: HTMLParagraphElement;
  submitButton: HTMLButtonElement;
}

function findElements(root: ParentNode): WidgetElements | null {
  const log = root.querySelector<HTMLOListElement>("#chat-log");
  const status = root.querySelector<HTMLParagraphElement>("#chat-status");
  const form = root.querySelector<HTMLFormElement>("#chat-form");
  const textarea = root.querySelector<HTMLTextAreaElement>("#chat-message");
  const counter = root.querySelector<HTMLParagraphElement>("#chat-count");
  const messageError = root.querySelector<HTMLParagraphElement>("#chat-message-error");
  const rollCheckbox = root.querySelector<HTMLInputElement>("#chat-roll");
  const modifierInput = root.querySelector<HTMLInputElement>("#chat-modifier");
  const modifierError = root.querySelector<HTMLParagraphElement>("#chat-modifier-error");
  const submitButton = root.querySelector<HTMLButtonElement>("#chat-submit");

  if (
    !log ||
    !status ||
    !form ||
    !textarea ||
    !counter ||
    !messageError ||
    !rollCheckbox ||
    !modifierInput ||
    !modifierError ||
    !submitButton
  ) {
    return null;
  }

  return {
    log,
    status,
    form,
    textarea,
    counter,
    messageError,
    rollCheckbox,
    modifierInput,
    modifierError,
    submitButton,
  };
}

export function mountChatWidget(opts?: {
  root?: ParentNode;
  send?: typeof sendChat;
  newSessionId?: () => string;
}): void {
  const root = opts?.root ?? document;
  const send = opts?.send ?? sendChat;
  const newSessionId = opts?.newSessionId ?? (() => crypto.randomUUID().replaceAll("-", ""));

  const els = findElements(root);
  if (!els) return;

  const {
    log,
    status,
    form,
    textarea,
    counter,
    messageError,
    rollCheckbox,
    modifierInput,
    modifierError,
    submitButton,
  } = els;

  const doc = resolveDocument(root);
  const sessionId = newSessionId();
  let pending = false;

  textarea.addEventListener("input", () => {
    counter.textContent = `${textarea.value.length}/${MAX_MESSAGE_CHARS}`;
  });

  rollCheckbox.addEventListener("change", () => {
    modifierInput.disabled = !rollCheckbox.checked;
  });

  textarea.addEventListener("keydown", (event) => {
    const keyboardEvent = event as KeyboardEvent;
    if (keyboardEvent.key !== "Enter" || keyboardEvent.shiftKey || keyboardEvent.isComposing) {
      return;
    }
    keyboardEvent.preventDefault();
    form.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
  });

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (pending) return;

    messageError.hidden = true;
    modifierError.hidden = true;

    const trimmedMessage = textarea.value.trim();
    if (trimmedMessage === "") {
      messageError.textContent = EMPTY_MESSAGE;
      messageError.hidden = false;
      textarea.focus();
      return;
    }

    const rollChecked = rollCheckbox.checked;
    let modifier: number | null = null;
    if (rollChecked && modifierInput.value.trim() !== "") {
      const raw = modifierInput.value.trim();
      const parsed = Number(raw);
      if (!Number.isInteger(parsed) || parsed < -10 || parsed > 10) {
        modifierError.textContent = MODIFIER_INVALID;
        modifierError.hidden = false;
        modifierInput.focus();
        return;
      }
      modifier = parsed;
    }

    log.appendChild(renderUserMessage(doc, trimmedMessage));
    textarea.value = "";
    counter.textContent = `0/${MAX_MESSAGE_CHARS}`;

    submitButton.disabled = true;
    submitButton.textContent = "Asking…";
    status.textContent = STATUS_START;
    pending = true;

    const body: ChatRequestBody = {
      message: trimmedMessage,
      roll: rollChecked,
      modifier,
      session_id: sessionId,
    };

    void send(body, {
      onStatus: (step) => {
        const text = STATUS_BY_STEP[step];
        if (text !== undefined) status.textContent = text;
      },
    })
      .then((outcome) => {
        if (outcome.type === "reply") {
          log.appendChild(renderReply(doc, outcome.reply));
          return;
        }
        log.appendChild(renderFailure(doc, outcome.message));
        if (textarea.value === "") {
          textarea.value = trimmedMessage;
        }
      })
      .finally(() => {
        pending = false;
        status.textContent = "";
        submitButton.disabled = false;
        submitButton.textContent = "Ask";
        const lastItem = log.lastElementChild;
        if (lastItem && typeof (lastItem as HTMLElement).scrollIntoView === "function") {
          (lastItem as HTMLElement).scrollIntoView({ block: "nearest" });
        }
        textarea.focus();
      });
  });
}
