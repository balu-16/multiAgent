import type { z } from "zod";
import {
  archiveDetailSchema,
  archiveListSchema,
  authResponseSchema,
  personasResponseSchema,
  startResponseSchema,
  type AgentPersona,
} from "@/types/chat";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
export const WS_URL = (process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000").replace(/\/$/, "");
export const SESSION_EXPIRED_EVENT = "backchannel:session-expired";

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

function detailMessage(value: unknown): string | undefined {
  if (typeof value !== "object" || value === null || !("detail" in value)) return;
  const detail = value.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail.flatMap((item: unknown) => {
      if (typeof item === "object" && item !== null && "msg" in item && typeof item.msg === "string") return [item.msg];
      return [];
    });
    return messages.join(". ") || undefined;
  }
}

async function request<T>(path: string, schema: z.ZodType<T> | null, options: RequestInit = {}, notifyUnauthorized = true): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(new DOMException("Request timed out", "TimeoutError")), 45_000);
  const onAbort = () => controller.abort(options.signal?.reason);
  if (options.signal?.aborted) onAbort();
  else options.signal?.addEventListener("abort", onAbort, { once: true });
  try {
    const response = await fetch(`${API_URL}${path}`, {
      ...options,
      credentials: "include",
      cache: "no-store",
      signal: controller.signal,
      headers: { ...(options.body ? { "Content-Type": "application/json" } : {}), ...options.headers },
    });
    if (!response.ok) {
      const body: unknown = await response.json().catch(() => null);
      if (response.status === 401 && notifyUnauthorized && !controller.signal.aborted && typeof window !== "undefined") {
        window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
      }
      throw new ApiError(response.status, detailMessage(body) ?? (response.status === 503
        ? "Backchannel is temporarily unavailable. Please try again in a moment."
        : response.status === 429 ? "A little too fast. Please wait a moment and try again."
          : "Something went wrong. Please try again."));
    }
    if (schema === null) return undefined as T;
    const result = schema.safeParse(await response.json());
    if (!result.success) throw new ApiError(502, "The server sent an unexpected response. Please try again.");
    return result.data;
  } finally {
    window.clearTimeout(timeout);
    options.signal?.removeEventListener("abort", onAbort);
  }
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof DOMException && error.name === "TimeoutError") return "That took longer than expected. Please try again.";
  if (error instanceof TypeError) return "Cannot reach Backchannel. Check your connection and try again.";
  if (error instanceof DOMException && error.name === "AbortError") return "The request was cancelled.";
  return "Something went wrong. Please try again.";
}

export const api = {
  me: (signal?: AbortSignal) => request("/api/auth/me", authResponseSchema, { signal }, false),
  login: (email: string, password: string) => request("/api/auth/login", authResponseSchema, {
    method: "POST", body: JSON.stringify({ email, password }),
  }, false),
  register: (email: string, password: string) => request("/api/auth/register", authResponseSchema, {
    method: "POST", body: JSON.stringify({ email, password }),
  }, false),
  logout: () => request<void>("/api/auth/logout", null, { method: "POST" }),
  generatePersonas: (topic: string, num_agents: number, signal?: AbortSignal) => request("/api/generate-personas", personasResponseSchema, {
    method: "POST", body: JSON.stringify({ topic, num_agents }), signal,
  }),
  startRoom: (topic: string, max_messages: number, personas: AgentPersona[], signal?: AbortSignal) => request("/api/rooms/start", startResponseSchema, {
    method: "POST", body: JSON.stringify({ topic, max_messages, personas }), signal,
  }),
  listChats: (cursor?: string, signal?: AbortSignal) => {
    const params = new URLSearchParams({ limit: "20" });
    if (cursor) params.set("cursor", cursor);
    return request(`/api/chats?${params}`, archiveListSchema, { signal });
  },
  getChat: (id: string, signal?: AbortSignal) => request(`/api/chats/${encodeURIComponent(id)}`, archiveDetailSchema, { signal }),
};
