// Usage: node launch.mjs <NN>
// Launches one cloud worker agent for ticket NN and records it in state.json.
import { Agent } from "@cursor/sdk";
import { REPO_URL, TICKETS } from "./tickets.mjs";
import { buildWorkerPrompt } from "./worker-prompt.mjs";
import { loadState, updateTicket } from "./state.mjs";

const nn = process.argv[2];
if (!TICKETS[nn]) {
  console.error(`unknown ticket: ${nn}`);
  process.exit(1);
}
const existing = loadState().tickets[nn];
if (existing && ["launched", "verifying", "merged"].includes(existing.status)) {
  console.error(`ticket ${nn} already ${existing.status} (agent ${existing.agentId})`);
  process.exit(1);
}

const apiKey = process.env.CURSOR_API_KEY;
if (!apiKey) {
  console.error("CURSOR_API_KEY not set");
  process.exit(1);
}

const prompt = buildWorkerPrompt(nn);

const agent = await Agent.create({
  apiKey,
  name: `foresight-ticket-${nn}`,
  model: { id: "gpt-5.6-sol", params: [{ id: "reasoning", value: "high" }] },
  cloud: {
    repos: [{ url: REPO_URL, startingRef: "main" }],
    autoCreatePR: true,
    skipReviewerRequest: true,
  },
});

console.log(`agentId: ${agent.agentId}`);

const run = await agent.send(prompt);
console.log(`runId: ${run.id}`);

updateTicket(nn, {
  status: "launched",
  agentId: agent.agentId,
  runId: run.id,
  launchedAt: new Date().toISOString(),
});

// Cloud runs survive caller disconnect; just release the local handle.
agent.close();
console.log(`ticket ${nn} launched`);
