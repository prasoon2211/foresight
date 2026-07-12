// Usage: node status.mjs [NN...]  — prints current status of tracked worker agents.
import { Agent } from "@cursor/sdk";
import { loadState } from "./state.mjs";

const apiKey = process.env.CURSOR_API_KEY;
const state = loadState();
const wanted = process.argv.slice(2);
const entries = Object.entries(state.tickets).filter(
  ([nn, t]) => t.agentId && (wanted.length === 0 || wanted.includes(nn))
);

for (const [nn, t] of entries) {
  try {
    const info = await Agent.get(t.agentId, { apiKey });
    console.log(
      JSON.stringify({
        ticket: nn,
        tracked: t.status,
        agentId: t.agentId,
        agentStatus: info.status,
        name: info.name,
        summary: (info.summary ?? "").slice(0, 300),
      })
    );
  } catch (err) {
    console.log(JSON.stringify({ ticket: nn, agentId: t.agentId, error: String(err) }));
  }
}
