// Widget copy, exact strings (spec 008 "User-Facing Copy → Widget"). The page intro paragraph
// lives in assistant.astro (story 005), not here.

export const STATUS_START = "Reading your message…";

export const STATUS_BY_STEP: Readonly<Record<string, string>> = {
  router: "Thinking…",
  retrieve: "Writing an answer from the rules…",
  answer_with_citations: "Checking the citations…",
  classify_move: "Explaining the move…",
};

export const NETWORK_FAILURE = "Couldn't reach the assistant. Check your connection and try again.";
export const INTERRUPTED = "The answer was interrupted. Please try again.";
export const UNAVAILABLE = "The assistant is unavailable right now. Please try again in a moment.";
export const EMPTY_MESSAGE = "Type a message first.";
export const MODIFIER_INVALID = "Enter a whole number from -10 to 10, or leave it empty.";
export const SOURCES_TITLE = "Sources";
export const CLOSEST_TITLE = "Closest sections in the rules";
export const NOT_STATED = "Not stated by this move.";
export const YOUR_ROLL = " (your roll)";
export const NEW_TAB = " (opens in a new tab)";
