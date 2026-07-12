import {
  apiRoutesAttachToRun,
  apiRoutesCreateOrganization,
  apiRoutesCreateSignal,
  apiRoutesGetRun,
  apiRoutesGetRunTranscript,
  apiRoutesGetSignal,
  apiRoutesListOrganizations,
  apiRoutesListRepos,
  apiRoutesListSignalRuns,
  apiRoutesListSignals,
  apiRoutesRerun,
  apiRoutesReviveRun,
  apiRoutesStopRunningRun,
} from "./generated/sdk.gen";
import { client } from "./generated/client.gen";
import type {
  AttachEndpointsOut,
  CreatedSignalOut,
  ManualSignalIn,
  OrgOut,
  RepoOut,
  RunOut,
  SessionTranscriptOut,
  SignalOut,
} from "./generated/types.gen";

client.setConfig({
  baseUrl: window.location.origin,
  credentials: "include",
});
client.interceptors.request.use((request) => {
  if (!["GET", "HEAD", "OPTIONS"].includes(request.method)) {
    const token = cookie("csrftoken");
    if (token) request.headers.set("X-CSRFToken", token);
  }
  return request;
});

const path = (orgId: number) => ({ org_id: orgId });
const runPath = (orgId: number, runId: number) => ({
  org_id: orgId,
  run_id: runId,
});

export const api = {
  async listOrgs(): Promise<OrgOut[]> {
    const { data } = await apiRoutesListOrganizations({ throwOnError: true });
    return data;
  },

  async createOrg(name: string): Promise<OrgOut> {
    const { data } = await apiRoutesCreateOrganization({
      body: { name },
      throwOnError: true,
    });
    return data;
  },

  async listRepos(orgId: number): Promise<RepoOut[]> {
    const { data } = await apiRoutesListRepos({
      path: path(orgId),
      throwOnError: true,
    });
    return data;
  },

  async listSignals(orgId: number): Promise<SignalOut[]> {
    const { data } = await apiRoutesListSignals({
      path: path(orgId),
      throwOnError: true,
    });
    return data;
  },

  async createSignal(orgId: number, signal: ManualSignalIn): Promise<CreatedSignalOut> {
    const { data } = await apiRoutesCreateSignal({
      path: path(orgId),
      body: signal,
      throwOnError: true,
    });
    return data;
  },

  async getSignal(orgId: number, signalId: number): Promise<SignalOut> {
    const { data } = await apiRoutesGetSignal({
      path: { org_id: orgId, signal_id: signalId },
      throwOnError: true,
    });
    return data;
  },

  async listRuns(orgId: number, signalId: number): Promise<RunOut[]> {
    const { data } = await apiRoutesListSignalRuns({
      path: { org_id: orgId, signal_id: signalId },
      throwOnError: true,
    });
    return data;
  },

  async getRun(orgId: number, runId: number): Promise<RunOut> {
    const { data } = await apiRoutesGetRun({
      path: runPath(orgId, runId),
      throwOnError: true,
    });
    return data;
  },

  async attach(orgId: number, runId: number): Promise<AttachEndpointsOut> {
    const { data } = await apiRoutesAttachToRun({
      path: runPath(orgId, runId),
      throwOnError: true,
    });
    return data;
  },

  async stop(orgId: number, runId: number): Promise<RunOut> {
    const { data } = await apiRoutesStopRunningRun({
      path: runPath(orgId, runId),
      throwOnError: true,
    });
    return data;
  },

  async rerun(orgId: number, signalId: number): Promise<RunOut> {
    const { data } = await apiRoutesRerun({
      path: { org_id: orgId, signal_id: signalId },
      throwOnError: true,
    });
    return data;
  },

  async transcript(orgId: number, runId: number): Promise<SessionTranscriptOut> {
    const { data } = await apiRoutesGetRunTranscript({
      path: runPath(orgId, runId),
      throwOnError: true,
    });
    return data;
  },

  async revive(orgId: number, runId: number): Promise<RunOut> {
    const { data } = await apiRoutesReviveRun({
      path: runPath(orgId, runId),
      throwOnError: true,
    });
    return data;
  },
};

type AuthResponse = {
  data?: { user?: { email?: string } };
  message?: string;
  hint?: string;
};

function cookie(name: string) {
  const prefix = `${name}=`;
  return document.cookie
    .split(";")
    .map((value) => value.trim())
    .find((value) => value.startsWith(prefix))
    ?.slice(prefix.length);
}

async function csrfToken() {
  let token = cookie("csrftoken");
  if (!token) {
    const response = await fetch("/api/csrf", { credentials: "include" });
    const payload = (await response.json()) as { csrf_token: string };
    token = cookie("csrftoken") || payload.csrf_token;
  }
  return token;
}

async function authRequest(
  pathname: string,
  body: object,
  acceptedStatuses = [200],
): Promise<AuthResponse> {
  const csrf = await csrfToken();
  const response = await fetch(pathname, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(csrf ? { "X-CSRFToken": csrf } : {}),
    },
    body: JSON.stringify(body),
  });
  const payload = (await response.json()) as AuthResponse;
  if (!acceptedStatuses.includes(response.status)) {
    throw new Error(payload.hint || payload.message || "Authentication failed.");
  }
  return payload;
}

export const auth = {
  login: (email: string, password: string) =>
    authRequest("/_allauth/browser/v1/auth/login", { email, password }),
  signup: (email: string, password: string) =>
    authRequest("/_allauth/browser/v1/auth/signup", { email, password }, [200, 401]),
  verifyEmail: (key: string) =>
    authRequest("/_allauth/browser/v1/auth/email/verify", { key }, [200, 401]),
};

export type {
  AttachEndpointsOut,
  OrgOut,
  RepoOut,
  RunOut,
  SessionTranscriptOut,
  SignalOut,
};
