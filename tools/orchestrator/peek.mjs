// Usage: node peek.mjs <NN> [--steps N] — show a worker's recent activity safely.
import { Agent } from "@cursor/sdk";
import { loadState } from "./state.mjs";

const nn = process.argv[2];
const t = loadState().tickets[nn];
if (!t?.agentId) {
  console.error(`no agent recorded for ticket ${nn}`);
  process.exit(1);
}

try {
  const run = await Agent.getRun(t.runId, { runtime: "cloud", agentId: t.agentId });
  console.log("run status:", run.status);
  const turns = await run.conversation();
  const steps = turns.flatMap((x) => (x.type === "agentConversationTurn" ? x.turn.steps : []));
  console.log("steps:", steps.length);
  for (const s of steps.slice(-8)) {
    if (s.type === "assistantMessage") console.log("[text]", s.message.text.slice(0, 200).replaceAll("\n", " "));
    else if (s.type === "toolCall") {
      const tc = s.message;
      const cmd = tc?.shell?.command ?? tc?.command ?? "";
      console.log("[tool]", (tc?.type ?? "?"), String(cmd).slice(0, 160).replaceAll("\n", " "));
    }
  }
} catch (err) {
  console.log("peek failed:", err.constructor?.name, "-", String(err.message).slice(0, 300));
}
