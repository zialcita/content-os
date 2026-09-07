"use client";

import { useEffect, useState } from "react";
import { api, type Evidence, type Source } from "@/lib/api";

export default function SourcesPage() {
  const [sources, setSources] = useState<Source[]>([]);
  const [hits, setHits] = useState<Evidence[]>([]);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [q, setQ] = useState("");
  const [evTitle, setEvTitle] = useState("");
  const [evContent, setEvContent] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [error, setError] = useState("");

  async function refresh() {
    const rows = await api<Source[]>("/v1/sources");
    setSources(rows);
    if (!sourceId && rows[0]) setSourceId(rows[0].id);
  }

  useEffect(() => {
    refresh().catch((err) => setError(String(err)));
  }, []);

  async function createSource(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api("/v1/sources", { method: "POST", body: JSON.stringify({ name, url }) });
      setName("");
      setUrl("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    }
  }

  async function addEvidence(e: React.FormEvent) {
    e.preventDefault();
    if (!sourceId) return;
    try {
      await api(`/v1/sources/${sourceId}/evidence`, {
        method: "POST",
        body: JSON.stringify({ title: evTitle, content: evContent }),
      });
      setEvTitle("");
      setEvContent("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    }
  }

  async function search(e: React.FormEvent) {
    e.preventDefault();
    try {
      setHits(await api<Evidence[]>(`/v1/evidence/search?q=${encodeURIComponent(q)}`));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    }
  }

  return (
    <>
      <h2>Sources</h2>
      <p className="lead">Research sources and evidence search (ILIKE now, pgvector later).</p>
      <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", marginBottom: 20 }}>
        <form className="card stack" onSubmit={(e) => void createSource(e)}>
          <h3>New source</h3>
          <input required value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" />
          <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://" />
          <button className="primary" type="submit">
            Add source
          </button>
        </form>
        <form className="card stack" onSubmit={(e) => void addEvidence(e)}>
          <h3>Add evidence</h3>
          <select value={sourceId} onChange={(e) => setSourceId(e.target.value)}>
            {sources.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
          <input required value={evTitle} onChange={(e) => setEvTitle(e.target.value)} placeholder="Title" />
          <textarea value={evContent} onChange={(e) => setEvContent(e.target.value)} placeholder="Excerpt" />
          <button type="submit">Save evidence</button>
        </form>
      </div>
      <form className="row" onSubmit={(e) => void search(e)} style={{ marginBottom: 16 }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search evidence" />
        <button className="primary" type="submit">
          Search
        </button>
      </form>
      {error && <p className="error">{error}</p>}
      <div className="card">
        <h3>Sources</h3>
        <ul>
          {sources.map((s) => (
            <li key={s.id}>
              {s.name} {s.url && <span className="muted">{s.url}</span>}
            </li>
          ))}
        </ul>
      </div>
      {hits.length > 0 && (
        <div className="grid" style={{ marginTop: 16 }}>
          {hits.map((h) => (
            <div className="card" key={h.id}>
              <h3>{h.title}</h3>
              <p>{h.content}</p>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
