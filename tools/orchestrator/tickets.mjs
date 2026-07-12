// Foresight V1 implementation tickets: paths and dependency edges.
// Mirrors the `Blocked by:` lines in .scratch/foresight-v1/issues/*.md.

export const REPO_URL = "https://github.com/prasoon2211/foresight";

export const TICKETS = {
  "07": { slug: "07-backend-scaffold", blockedBy: [] },
  "08": { slug: "08-tracer-bullet-manual-signal-to-run", blockedBy: ["07"] },
  "09": { slug: "09-auth-orgs-api-tokens", blockedBy: ["08"] },
  "10": { slug: "10-failure-durability-run-control", blockedBy: ["08"] },
  "11": { slug: "11-github-issue-to-run", blockedBy: ["08", "09"] },
  "12": { slug: "12-harness-prompt-and-result-contract", blockedBy: ["08", "11"] },
  "13": { slug: "13-daytona-and-snapshots", blockedBy: ["08", "12"] },
  "14": { slug: "14-dashboard-signals-and-run-room", blockedBy: ["09", "10", "11", "13"] },
  "15": { slug: "15-dashboard-onboarding-and-settings", blockedBy: ["09", "11", "13", "14"] },
  "16": { slug: "16-deployment-packaging", blockedBy: ["14", "15"] },
};

export function ticketPath(nn) {
  return `.scratch/foresight-v1/issues/${TICKETS[nn].slug}.md`;
}

/** Tickets whose blockers are all in `mergedSet` and which aren't launched/merged themselves. */
export function frontier(state) {
  const merged = new Set(
    Object.entries(state.tickets ?? {})
      .filter(([, t]) => t.status === "merged")
      .map(([nn]) => nn)
  );
  return Object.keys(TICKETS).filter((nn) => {
    const st = state.tickets?.[nn]?.status;
    if (st === "merged" || st === "launched" || st === "verifying") return false;
    return TICKETS[nn].blockedBy.every((dep) => merged.has(dep));
  });
}
