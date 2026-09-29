import axios, { AxiosError } from "axios";
import type { ApiError } from "./types";

export const baseURL = (
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"
).replace(/\/$/, "");
export const publicClient = axios.create({ baseURL, timeout: 40000 });
export const client = axios.create({ baseURL, timeout: 40000 });
let access = "";
let refresh = "";
let refreshFlight: Promise<string> | null = null;
let epoch = 0;
const listeners = new Set<() => void>();
export const session = {
  get: () => access,
  set: (tokens: { access: string; refresh: string }) => {
    epoch++;
    access = tokens.access;
    refresh = tokens.refresh;
    listeners.forEach((fn) => fn());
  },
  clear: () => {
    epoch++;
    access = "";
    refresh = "";
    listeners.forEach((fn) => fn());
  },
  subscribe: (fn: () => void) => {
    listeners.add(fn);
    return () => {
      listeners.delete(fn);
    };
  },
};
client.interceptors.request.use((config) => {
  if (access) config.headers.Authorization = `Bearer ${access}`;
  return config;
});
client.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as
      (NonNullable<typeof error.config> & { _retried?: boolean }) | undefined;
    if (
      error.response?.status !== 401 ||
      !original ||
      original._retried ||
      !refresh
    ) {
      if (error.response?.status === 401) session.clear();
      return Promise.reject(error);
    }
    original._retried = true;
    const generation = epoch;
    try {
      if (!refreshFlight)
        refreshFlight = publicClient
          .post<{ access: string }>("/api/auth/token/refresh/", { refresh })
          .then(({ data }) => {
            if (epoch !== generation) throw new Error("Session changed");
            access = data.access;
            return access;
          })
          .finally(() => {
            refreshFlight = null;
          });
      const token = await refreshFlight;
      original.headers.Authorization = `Bearer ${token}`;
      return client.request(original);
    } catch (refreshError) {
      if (epoch === generation) session.clear();
      return Promise.reject(refreshError);
    }
  },
);

export function normalizeError(error: unknown): ApiError {
  if (axios.isAxiosError(error)) {
    const statusCode = error.response?.status;
    const data = error.response?.data;
    const fieldErrors: Record<string, string> = {};
    if (data && typeof data === "object" && !Array.isArray(data)) {
      for (const [key, value] of Object.entries(data))
        if (key !== "detail" && key !== "non_field_errors")
          fieldErrors[key] = Array.isArray(value)
            ? value.join(" ")
            : String(value);
    }
    const message =
      typeof data?.detail === "string"
        ? data.detail
        : Array.isArray(data?.non_field_errors)
          ? data.non_field_errors.join(" ")
          : Array.isArray(data)
            ? data.join(" ")
            : Object.values(fieldErrors)[0] ||
              (statusCode === 403
                ? "This account does not have administrator access."
                : statusCode === 404
                  ? "This record could not be found."
                  : statusCode
                    ? "The request could not be completed. Please try again."
                    : "Unable to reach the server. Check your connection and try again.");
    return { message, fieldErrors, statusCode };
  }
  return {
    message:
      error instanceof Error
        ? error.message
        : "Something went wrong. Please try again.",
    fieldErrors: {},
  };
}
