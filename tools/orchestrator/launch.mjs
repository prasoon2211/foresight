// Usage: node launch.mjs <NN> ["extra orchestrator note appended to the prompt"]
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

const extraNote = process.argv[3];
const prompt =
  buildWorkerPrompt(nn) +
  (extraNote ? `\n\n## Note from the orchestrator\n\n${extraNote}` : "");

let agent, run;
try {
  agent = await Agent.create({
    apiKey,
    name: `foresight-ticket-${nn}`,
    model: {
      id: "gpt-5.6-sol",
      params: [
        { id: "context", value: "1m" },
        { id: "reasoning", value: "high" },
        { id: "fast", value: "false" },
      ],
    },
    cloud: {
      repos: [{ url: REPO_URL, startingRef: "main" }],
      autoCreatePR: true,
      skipReviewerRequest: true,
    },
  });
  console.log(`agentId: ${agent.agentId}`);
  run = await agent.send(prompt);
  console.log(`runId: ${run.id}`);
} catch (err) {
  console.error(
    `launch failed: ${err.constructor?.name}: ${err.message} | code: ${err.code} | status: ${err.status} | retryable: ${err.isRetryable}`
  );
  if (err.helpUrl) console.error(`helpUrl: ${err.helpUrl}`);
  process.exit(1);
}

updateTicket(nn, {
  status: "launched",
  agentId: agent.agentId,
  runId: run.id,
  launchedAt: new Date().toISOString(),
});

// Cloud runs survive caller disconnect; just release the local handle.
agent.close();
console.log(`ticket ${nn} launched`);
