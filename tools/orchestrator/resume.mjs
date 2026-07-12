// Usage: node resume.mjs <NN> "follow-up message"
// Sends a follow-up prompt to the ticket's existing worker agent and waits.
import { Agent } from "@cursor/sdk";
import { loadState, updateTicket } from "./state.mjs";

const nn = process.argv[2];
const message = process.argv[3];
if (!message) {
  console.error("usage: node resume.mjs <NN> \"message\"");
  process.exit(1);
}
const t = loadState().tickets[nn];
if (!t?.agentId) {
  console.error(`no agent recorded for ticket ${nn}`);
  process.exit(1);
}

const agent = await Agent.resume(t.agentId, { apiKey: process.env.CURSOR_API_KEY });
const run = await agent.send(message);
console.log(`runId: ${run.id}`);
updateTicket(nn, { status: "launched", runId: run.id, resumedAt: new Date().toISOString() });
const result = await run.wait();
console.log("--- run status:", result.status);
if (result.git?.branches?.length) {
  for (const b of result.git.branches) {
    console.log(`--- branch: ${b.branch ?? "?"} pr: ${b.prUrl ?? "none"}`);
    if (b.prUrl) updateTicket(nn, { prUrl: b.prUrl, branch: b.branch });
  }
}
if (result.error) console.log("--- error:", JSON.stringify(result.error));
console.log("--- final report ---");
console.log(result.result ?? "(no result text)");
updateTicket(nn, { status: "verifying", finishedAt: new Date().toISOString() });
agent.close();
