export const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const KEY = "contentos_api_key";

export function getApiKey(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(KEY) || "";
}

export function setApiKey(key: string): void {
  localStorage.setItem(KEY, key);
}

export async function api<T>(
  path: string,
  init: RequestInit = {},
  apiKey = getApiKey(),
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (apiKey) headers.set("X-API-Key", apiKey);
  const res = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${text}`);
  }
  return res.json() as Promise<T>;
}

export type Workspace = {
  id: string;
  name: string;
  api_key?: string;
  api_key_prefix: string;
  spend_usd: number;
  spend_limit_usd: number;
};

export type Persona = {
  id: string;
  name: string;
  description: string;
  tone: string;
  audience: string;
  brand_id: string | null;
};

export type Source = {
  id: string;
  name: string;
  url: string;
  source_type: string;
  status: string;
};

export type Evidence = {
  id: string;
  source_id: string;
  title: string;
  content: string;
  url: string;
};

export type Scene = {
  id: string;
  idx: number;
  script_text: string;
  visual_direction: string;
  aroll_asset_id: string | null;
  broll_asset_id: string | null;
};

export type Video = {
  id: string;
  title: string;
  topic: string;
  status: string;
  script_draft: string;
  script_final: string;
  published_url: string;
  error: string;
  scenes: Scene[];
  persona_id: string | null;
};

export type Clip = {
  id: string;
  title: string;
  start_s: number;
  end_s: number;
};
