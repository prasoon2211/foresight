// Usage: node frontier.mjs — prints tickets ready to launch given state.json.
import { frontier } from "./tickets.mjs";
import { loadState } from "./state.mjs";

const state = loadState();
console.log("merged:", Object.entries(state.tickets).filter(([, t]) => t.status === "merged").map(([n]) => n).join(", ") || "(none)");
console.log("in-flight:", Object.entries(state.tickets).filter(([, t]) => ["launched", "verifying"].includes(t.status)).map(([n]) => n).join(", ") || "(none)");
console.log("frontier:", frontier(state).join(", ") || "(none)");
