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

async function authRequest(pathname: string, body: object): Promise<AuthResponse> {
  const response = await fetch(pathname, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = (await response.json()) as AuthResponse;
  if (!response.ok) {
    throw new Error(payload.hint || payload.message || "Authentication failed.");
  }
  return payload;
}

export const auth = {
  login: (email: string, password: string) =>
    authRequest("/_allauth/browser/v1/auth/login", { email, password }),
  signup: (email: string, password: string) =>
    authRequest("/_allauth/browser/v1/auth/signup", { email, password }),
  verifyEmail: (key: string) =>
    authRequest("/_allauth/browser/v1/auth/email/verify", { key }),
};

export type {
  AttachEndpointsOut,
  OrgOut,
  RepoOut,
  RunOut,
  SessionTranscriptOut,
  SignalOut,
};
