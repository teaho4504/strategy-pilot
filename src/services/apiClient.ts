export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

function toApiUrl(path: string) {
  if (/^https?:\/\//.test(path)) return path;
  if (!API_BASE_URL) return path;
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

export async function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(toApiUrl(path), {
    ...init,
    method: "GET",
    headers: {
      Accept: "application/json",
      ...init?.headers,
    },
  });

  let body: unknown = null;
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    body = await response.json();
  } else {
    body = await response.text();
  }

  if (!response.ok) {
    const message = typeof body === "object" && body && "detail" in body
      ? String((body as { detail: unknown }).detail)
      : `API request failed: ${response.status}`;
    throw new ApiError(message, response.status, body);
  }

  return body as T;
}

export function formatQueryUpdatedAt(updatedAt: number) {
  if (!updatedAt) return "갱신 전";
  return new Intl.DateTimeFormat("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(updatedAt));
}

export function errorMessage(error: unknown) {
  if (error instanceof Error) return error.message;
  return "데이터를 불러오지 못했습니다.";
}
