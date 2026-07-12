import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const STATE_PATH = join(dirname(fileURLToPath(import.meta.url)), "state.json");

export function loadState() {
  if (!existsSync(STATE_PATH)) return { tickets: {} };
  return JSON.parse(readFileSync(STATE_PATH, "utf8"));
}

export function saveState(state) {
  writeFileSync(STATE_PATH, JSON.stringify(state, null, 2) + "\n");
}

export function updateTicket(nn, patch) {
  const state = loadState();
  state.tickets[nn] = { ...(state.tickets[nn] ?? {}), ...patch };
  saveState(state);
  return state.tickets[nn];
}
