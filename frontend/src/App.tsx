import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, lazy, Suspense, useCallback, useEffect, useState } from "react";
import {
  Link,
  Navigate,
  Route,
  Routes,
  useNavigate,
  useParams,
} from "react-router-dom";

import {
  api,
  auth,
  type AttachEndpointsOut,
  type RunOut,
  type SignalOut,
} from "./api";

const Terminal = lazy(() =>
  import("./Terminal").then((module) => ({ default: module.Terminal })),
);

const activeStates = new Set(["queued", "provisioning", "running"]);
const timeline = ["queued", "provisioning", "running", "awaiting_review", "done"];

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "The request failed.";
}

function useIds() {
  const params = useParams();
  return {
    orgId: Number(params.orgId),
    signalId: Number(params.signalId),
    runId: Number(params.runId),
  };
}

export function App() {
  return (
    <Routes>
      <Route path="/verify-email/:key" element={<VerifyEmail />} />
      <Route path="*" element={<DashboardGate />} />
    </Routes>
  );
}

function DashboardGate() {
  const queryClient = useQueryClient();
  const orgs = useQuery({ queryKey: ["orgs"], queryFn: api.listOrgs, retry: false });

  if (orgs.isPending) return <Centered>Opening Foresight…</Centered>;
  if (orgs.isError) {
    return <Login onSuccess={() => queryClient.invalidateQueries({ queryKey: ["orgs"] })} />;
  }
  if (!orgs.data.length) return <CreateOrg />;

  return (
    <Routes>
      <Route path="/" element={<Navigate to={`/orgs/${orgs.data[0].id}/signals`} replace />} />
      <Route path="/orgs/:orgId/signals" element={<Shell><Signals /></Shell>} />
      <Route
        path="/orgs/:orgId/signals/:signalId"
        element={<Shell><SignalDetail /></Shell>}
      />
      <Route path="/orgs/:orgId/runs/:runId" element={<Shell><RunRoom /></Shell>} />
      <Route
        path="*"
        element={<Navigate to={`/orgs/${orgs.data[0].id}/signals`} replace />}
      />
    </Routes>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return <main className="centered">{children}</main>;
}

function Shell({ children }: { children: React.ReactNode }) {
  const { orgId } = useIds();
  return (
    <div className="app-shell">
      <header>
        <Link className="brand" to={`/orgs/${orgId}/signals`}>
          <span className="brand-mark">F</span>
          <span>Foresight</span>
        </Link>
        <span className="environment">Control plane</span>
      </header>
      <main>{children}</main>
    </div>
  );
}

function Login({ onSuccess }: { onSuccess: () => void }) {
  const [signup, setSignup] = useState(false);
  const mutation = useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) =>
      signup ? auth.signup(email, password) : auth.login(email, password),
    onSuccess,
  });
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    mutation.mutate({
      email: String(form.get("email")),
      password: String(form.get("password")),
    });
  };
  return (
    <Centered>
      <section className="auth-card">
        <span className="brand-mark large">F</span>
        <p className="eyebrow">AUTONOMOUS SOFTWARE FACTORY</p>
        <h1>{signup ? "Create your account" : "Welcome back"}</h1>
        <form onSubmit={submit}>
          <label>Email<input name="email" type="email" required autoFocus /></label>
          <label>Password<input name="password" type="password" minLength={8} required /></label>
          {mutation.isError && <p className="error">{errorMessage(mutation.error)}</p>}
          {signup && mutation.isSuccess ? (
            <p className="notice">Check your email, verify the account, then sign in.</p>
          ) : (
            <button className="primary" disabled={mutation.isPending}>
              {mutation.isPending ? "Working…" : signup ? "Sign up" : "Sign in"}
            </button>
          )}
        </form>
        <button className="text-button" onClick={() => setSignup((value) => !value)}>
          {signup ? "Already have an account? Sign in" : "Need an account? Sign up"}
        </button>
      </section>
    </Centered>
  );
}

function VerifyEmail() {
  const { key = "" } = useParams();
  const verification = useMutation({ mutationFn: () => auth.verifyEmail(key) });
  return (
    <Centered>
      <section className="auth-card">
        <span className="brand-mark large">F</span>
        <h1>Verify your email</h1>
        {verification.isSuccess ? (
          <>
            <p className="notice">Email verified. You can sign in now.</p>
            <Link className="button primary" to="/">Continue</Link>
          </>
        ) : (
          <>
            {verification.isError && <p className="error">{errorMessage(verification.error)}</p>}
            <button className="primary" onClick={() => verification.mutate()}>
              Verify email
            </button>
          </>
        )}
      </section>
    </Centered>
  );
}

function CreateOrg() {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: api.createOrg,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["orgs"] }),
  });
  return (
    <Centered>
      <section className="auth-card">
        <h1>Name your org</h1>
        <p className="muted">This is the tenant that owns your signals, repos, and runs.</p>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            mutation.mutate(String(new FormData(event.currentTarget).get("name")));
          }}
        >
          <label>Org name<input name="name" required autoFocus /></label>
          <button className="primary">Create org</button>
        </form>
      </section>
    </Centered>
  );
}

function Signals() {
  const { orgId } = useIds();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const signals = useQuery({
    queryKey: ["signals", orgId],
    queryFn: () => api.listSignals(orgId),
    refetchInterval: 5000,
  });
  const repos = useQuery({ queryKey: ["repos", orgId], queryFn: () => api.listRepos(orgId) });
  const create = useMutation({
    mutationFn: (input: { repo_id: number; title: string; body: string }) =>
      api.createSignal(orgId, input),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ["signals", orgId] });
      navigate(`/orgs/${orgId}/runs/${created.run_id}`);
    },
  });
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    create.mutate({
      repo_id: Number(form.get("repo")),
      title: String(form.get("title")),
      body: String(form.get("body")),
    });
  };
  return (
    <>
      <div className="page-title">
        <div><p className="eyebrow">WORK QUEUE</p><h1>Signals</h1></div>
        <span className="live-dot">Live</span>
      </div>
      <section className="create-signal panel">
        <h2>Create a manual signal</h2>
        <form onSubmit={submit}>
          <select name="repo" aria-label="Target repo" required defaultValue="">
            <option value="" disabled>Target repo</option>
            {repos.data?.map((repo) => <option key={repo.id} value={repo.id}>{repo.full_name}</option>)}
          </select>
          <input name="title" placeholder="What needs to change?" required />
          <textarea name="body" placeholder="Context, constraints, and acceptance criteria" required />
          {create.isError && <p className="error">{errorMessage(create.error)}</p>}
          <button className="primary" disabled={create.isPending || !repos.data?.length}>
            {create.isPending ? "Dispatching…" : "Dispatch signal"}
          </button>
        </form>
      </section>
      <section className="signal-list" aria-label="Signals">
        {signals.isPending && <p className="muted">Loading signals…</p>}
        {signals.data?.map((signal) => <SignalRow key={signal.id} signal={signal} orgId={orgId} />)}
        {signals.data?.length === 0 && <div className="empty">No signals yet.</div>}
      </section>
    </>
  );
}

function SignalRow({ signal, orgId }: { signal: SignalOut; orgId: number }) {
  return (
    <Link className={`signal-row ${signal.stranded ? "stranded" : ""}`} to={`/orgs/${orgId}/signals/${signal.id}`}>
      <div>
        <div className="row-title"><span>#{signal.id}</span><strong>{signal.title}</strong></div>
        <p>{signal.repo_full_name} · {signal.source.replace("_", " ")}</p>
      </div>
      <div className="row-status">
        {signal.stranded && <span className="badge danger">Stranded</span>}
        <StatusBadge status={signal.outcome_status} />
      </div>
    </Link>
  );
}

function SignalDetail() {
  const { orgId, signalId } = useIds();
  const signal = useQuery({
    queryKey: ["signal", orgId, signalId],
    queryFn: () => api.getSignal(orgId, signalId),
  });
  const runs = useQuery({
    queryKey: ["runs", orgId, signalId],
    queryFn: () => api.listRuns(orgId, signalId),
    refetchInterval: 5000,
  });
  if (!signal.data) return <p className="muted">Loading signal…</p>;
  return (
    <>
      <Link className="back" to={`/orgs/${orgId}/signals`}>← Signals</Link>
      <div className="page-title">
        <div><p className="eyebrow">SIGNAL #{signalId}</p><h1>{signal.data.title}</h1></div>
        <StatusBadge status={signal.data.outcome_status} />
      </div>
      {signal.data.stranded && (
        <div className="warning">This signal is stranded because its repo is disconnected. Reconnect the repo to make it actionable.</div>
      )}
      <section className="panel prose">
        <div className="meta">{signal.data.repo_full_name} · {signal.data.source.replace("_", " ")}</div>
        <p>{signal.data.body}</p>
        {signal.data.origin_url && <a href={signal.data.origin_url} target="_blank">Open origin ↗</a>}
      </section>
      <h2>Run history</h2>
      <section className="run-history">
        {runs.data?.map((run, index) => (
          <Link key={run.id} to={`/orgs/${orgId}/runs/${run.id}`} className="run-row">
            <span>Attempt {index + 1}</span>
            <StatusBadge status={run.state} />
            <span className="run-summary">
              {run.result?.summary ||
                (run.failure_reason
                  ? `${run.failure_reason.replaceAll("_", " ")}${run.failure_detail ? ` — ${run.failure_detail}` : ""}`
                  : "No result yet")}
            </span>
            <time>{new Date(run.created_at).toLocaleString()}</time>
            <span>Open run room →</span>
          </Link>
        ))}
      </section>
    </>
  );
}

function RunRoom() {
  const { orgId, runId } = useIds();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [attach, setAttach] = useState<AttachEndpointsOut | null>(null);
  const [terminalUrl, setTerminalUrl] = useState("");
  const [showTranscript, setShowTranscript] = useState(false);
  const run = useQuery({
    queryKey: ["run", orgId, runId],
    queryFn: () => api.getRun(orgId, runId),
    refetchInterval: (query) =>
      activeStates.has(query.state.data?.state ?? "") ? 2000 : 10000,
  });
  const signal = useQuery({
    queryKey: ["signal-for-run", orgId, run.data?.signal_id],
    queryFn: () => api.getSignal(orgId, run.data!.signal_id),
    enabled: Boolean(run.data),
  });
  const attachMutation = useMutation({
    mutationFn: () => api.attach(orgId, runId),
    onSuccess: setAttach,
  });
  const stop = useMutation({
    mutationFn: () => api.stop(orgId, runId),
    onSuccess: (updated) => queryClient.setQueryData(["run", orgId, runId], updated),
  });
  const rerun = useMutation({
    mutationFn: () => api.rerun(orgId, run.data!.signal_id),
    onSuccess: (created) => navigate(`/orgs/${orgId}/runs/${created.id}`),
  });
  const revive = useMutation({
    mutationFn: () => api.revive(orgId, runId),
    onSuccess: (updated) => queryClient.setQueryData(["run", orgId, runId], updated),
  });
  const transcript = useQuery({
    queryKey: ["transcript", orgId, runId],
    queryFn: () => api.transcript(orgId, runId),
    enabled: showTranscript,
  });
  useEffect(() => {
    if (!attach) return;
    const refreshIn = Math.max(Date.parse(attach.expires_at) - Date.now() - 30_000, 1_000);
    const timer = window.setTimeout(() => attachMutation.mutate(), refreshIn);
    return () => window.clearTimeout(timer);
  }, [attach?.expires_at]);
  const closeTerminal = useCallback(() => setTerminalUrl(""), []);
  const reconnectTerminal = useCallback(() => {
    setTerminalUrl("");
    window.setTimeout(() => {
      api.attach(orgId, runId).then((fresh) => setTerminalUrl(fresh.terminal_websocket_url));
    }, 1_000);
  }, [orgId, runId]);

  if (!run.data) return <p className="muted">Loading run room…</p>;
  const current = run.data;
  const attachable = !current.sandbox_archived_at && Boolean(current.state !== "queued");
  const copyTui = () =>
    api.attach(orgId, runId).then((fresh) => navigator.clipboard.writeText(fresh.tui_command));
  const openTerminal = () =>
    api.attach(orgId, runId).then((fresh) => setTerminalUrl(fresh.terminal_websocket_url));

  return (
    <>
      <Link className="back" to={`/orgs/${orgId}/signals/${current.signal_id}`}>← Signal</Link>
      <div className="page-title">
        <div>
          <p className="eyebrow">RUN #{runId}</p>
          <h1>{signal.data?.title ?? `Signal #${current.signal_id}`}</h1>
        </div>
        <StatusBadge status={current.state} />
      </div>
      <StateTimeline run={current} />
      <div className="run-grid">
        <section className="panel session-panel">
          <div className="panel-title">
            <div><p className="eyebrow">LIVE SESSION</p><h2>Agent workspace</h2></div>
            {attachable && (
              <button onClick={() => attachMutation.mutate()}>
                {attach ? "Refresh signed URL" : "Watch session"}
              </button>
            )}
          </div>
          {attach ? (
            <>
              <div className="session-credential">
                OpenCode login: <code>{attach.web_username}</code>
                <button onClick={() => navigator.clipboard.writeText(attach.web_password)}>
                  Copy password
                </button>
              </div>
              <iframe title="Live OpenCode session" src={attach.web_url} />
            </>
          ) : (
            <div className="session-placeholder">
              {current.sandbox_archived_at
                ? "Revive the archived sandbox to continue this session."
                : current.state === "queued"
                  ? "The session will be available after provisioning."
                  : "Signed access is minted on demand and never cached."}
            </div>
          )}
          {attachMutation.isError && <p className="error">{errorMessage(attachMutation.error)}</p>}
        </section>
        <aside>
          <section className="panel">
            <p className="eyebrow">TAKE CONTROL</p>
            <div className="action-stack">
              <button disabled={!attachable} onClick={openTerminal}>Open web terminal</button>
              <button disabled={!attachable} onClick={copyTui}>Copy local TUI command</button>
              {activeStates.has(current.state) && (
                <button className="danger-button" onClick={() => stop.mutate()}>Stop run</button>
              )}
              {["failed", "done"].includes(current.state) && (
                <button onClick={() => rerun.mutate()}>Re-run signal</button>
              )}
              {current.revivable && (
                <button onClick={() => revive.mutate()}>Revive archived sandbox</button>
              )}
            </div>
          </section>
          <ResultCard run={current} />
        </aside>
      </div>
      {terminalUrl && (
        <section className="panel terminal-panel">
          <div className="panel-title"><h2>Sandbox terminal</h2><button onClick={closeTerminal}>Close</button></div>
          <Suspense fallback={<p className="muted">Loading terminal…</p>}>
            <Terminal websocketUrl={terminalUrl} onDisconnect={reconnectTerminal} />
          </Suspense>
        </section>
      )}
      {current.has_transcript && (
        <section className="panel transcript-panel">
          <div className="panel-title">
            <div><p className="eyebrow">DURABLE RECORD</p><h2>Session transcript</h2></div>
            <button onClick={() => setShowTranscript((value) => !value)}>
              {showTranscript ? "Hide" : "View full transcript"}
            </button>
          </div>
          {showTranscript && transcript.data?.messages.map((message, index) => (
            <article className={`message ${message.role}`} key={`${message.role}-${index}`}>
              <strong>{message.role}</strong><pre>{message.text}</pre>
            </article>
          ))}
        </section>
      )}
    </>
  );
}

function StateTimeline({ run }: { run: RunOut }) {
  const currentIndex = timeline.indexOf(run.state);
  return (
    <ol className="timeline">
      {timeline.map((state, index) => (
        <li
          key={state}
          className={
            run.state === "failed"
              ? ""
              : index < currentIndex ? "complete" : index === currentIndex ? "current" : ""
          }
        >
          <span>{index + 1}</span>{state.replace("_", " ")}
        </li>
      ))}
      {run.state === "failed" && <li className="failed"><span>!</span>failed</li>}
    </ol>
  );
}

function ResultCard({ run }: { run: RunOut }) {
  if (run.failure_reason) {
    return (
      <section className="panel failure-card">
        <p className="eyebrow">FAILURE DETAIL</p>
        <h2>{run.failure_reason.replaceAll("_", " ")}</h2>
        <pre>{run.failure_detail || "No additional detail was reported."}</pre>
      </section>
    );
  }
  if (!run.result) return <section className="panel muted">No result reported yet.</section>;
  return (
    <section className="panel result-card">
      <p className="eyebrow">RESULT</p>
      <h2>{run.result.status.replaceAll("_", " ")}</h2>
      <p>{run.result.summary}</p>
      <div className="confidence">{Math.round(run.result.confidence * 100)}% confidence</div>
      {run.result.pr_url && <a className="button primary" href={run.result.pr_url} target="_blank">Open pull request ↗</a>}
    </section>
  );
}

function StatusBadge({ status }: { status: string }) {
  const tone = status === "failed" || status === "stranded" ? "danger" : status === "done" ? "success" : "";
  return <span className={`badge ${tone}`}>{status.replaceAll("_", " ")}</span>;
}
