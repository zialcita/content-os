"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api, getApiKey, setApiKey, type Workspace } from "@/lib/api";

const LINKS = [
  ["/videos", "Videos"],
  ["/personas", "Personas"],
  ["/sources", "Sources"],
  ["/review", "Review"],
] as const;

export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const [ready, setReady] = useState(false);
  const [key, setKey] = useState("");
  const [ws, setWs] = useState<Workspace | null>(null);
  const [name, setName] = useState("Demo Studio");
  const [error, setError] = useState("");

  useEffect(() => {
    const existing = getApiKey();
    setKey(existing);
    setReady(true);
    if (existing) {
      api<Workspace>("/v1/workspaces/me", {}, existing)
        .then(setWs)
        .catch(() => undefined);
    }
  }, []);

  async function bootstrap() {
    setError("");
    try {
      const created = await api<Workspace>("/v1/workspaces", {
        method: "POST",
        body: JSON.stringify({ name }),
      });
      if (!created.api_key) throw new Error("Workspace created without API key");
      setApiKey(created.api_key);
      setKey(created.api_key);
      setWs(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    }
  }

  if (!ready) return null;
  if (!key) {
    return (
      <div className="boot card">
        <h2>Content OS</h2>
        <p className="lead">Create a workspace to get an API key. No provider keys required.</p>
        <form
          className="stack"
          onSubmit={(e) => {
            e.preventDefault();
            void bootstrap();
          }}
        >
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Workspace name" />
          <button className="primary" type="submit">
            Create workspace
          </button>
        </form>
        {error && <p className="error">{error}</p>}
      </div>
    );
  }

  return (
    <div className="shell">
      <nav className="side">
        <h1>Content OS</h1>
        {LINKS.map(([href, label]) => (
          <Link key={href} href={href} className={path.startsWith(href) ? "active" : ""}>
            {label}
          </Link>
        ))}
        <p className="muted" style={{ marginTop: 24 }}>
          {ws ? `${ws.name} · $${ws.spend_usd.toFixed(3)} / $${ws.spend_limit_usd}` : key.slice(0, 12)}
        </p>
      </nav>
      <main>{children}</main>
    </div>
  );
}
