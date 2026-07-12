// Usage: node watch.mjs <NN> [--interval-s 60]
// Blocks until ticket NN's worker run reaches a terminal state, then prints the
// final report (last assistant message) and git info.
import { Agent } from "@cursor/sdk";
import { loadState, updateTicket } from "./state.mjs";

const nn = process.argv[2];
const intervalIdx = process.argv.indexOf("--interval-s");
const intervalS = intervalIdx > 0 ? Number(process.argv[intervalIdx + 1]) : 60;

const t = loadState().tickets[nn];
if (!t?.agentId) {
  console.error(`no agent recorded for ticket ${nn}`);
  process.exit(1);
}
const apiKey = process.env.CURSOR_API_KEY;

let lastStatus = "";
let run;
for (;;) {
  try {
    run = await Agent.getRun(t.runId, { runtime: "cloud", agentId: t.agentId, apiKey });
  } catch (err) {
    console.log(`[${new Date().toISOString()}] Agent.getRun error: ${err}`);
    await sleep(intervalS * 1000);
    continue;
  }
  if (run.status !== lastStatus) {
    console.log(`[${new Date().toISOString()}] run status: ${run.status}`);
    lastStatus = run.status;
  }
  if (run.status && run.status !== "running") break;
  await sleep(intervalS * 1000);
}

try {
  console.log("--- run status:", run.status);
  if (run.git?.branches?.length) {
    for (const b of run.git.branches) {
      console.log(`--- branch: ${b.branch ?? "?"} pr: ${b.prUrl ?? "none"}`);
      if (b.prUrl) updateTicket(nn, { prUrl: b.prUrl, branch: b.branch });
    }
  }
  if (run.error) console.log("--- error:", JSON.stringify(run.error));
  console.log("--- final report ---");
  console.log(run.result ?? "(no result text)");
} catch (err) {
  console.log("failed to fetch run result:", String(err));
}

updateTicket(nn, { status: "verifying", finishedAt: new Date().toISOString() });
console.log(`ticket ${nn} run terminal; state -> verifying`);

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}
