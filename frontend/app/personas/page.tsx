"use client";

import { useEffect, useState } from "react";
import { api, type Persona } from "@/lib/api";

export default function PersonasPage() {
  const [rows, setRows] = useState<Persona[]>([]);
  const [name, setName] = useState("");
  const [tone, setTone] = useState("");
  const [audience, setAudience] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");

  async function refresh() {
    setRows(await api<Persona[]>("/v1/personas"));
  }

  useEffect(() => {
    refresh().catch((err) => setError(String(err)));
  }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api("/v1/personas", {
        method: "POST",
        body: JSON.stringify({ name, tone, audience, description }),
      });
      setName("");
      setTone("");
      setAudience("");
      setDescription("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    }
  }

  return (
    <>
      <h2>Personas</h2>
      <p className="lead">Voice and audience used when drafting scripts.</p>
      <form className="card stack" onSubmit={(e) => void create(e)} style={{ marginBottom: 20 }}>
        <input required value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" />
        <input value={tone} onChange={(e) => setTone(e.target.value)} placeholder="Tone" />
        <input value={audience} onChange={(e) => setAudience(e.target.value)} placeholder="Audience" />
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Description" />
        <button className="primary" type="submit">
          Add persona
        </button>
      </form>
      {error && <p className="error">{error}</p>}
      <div className="grid">
        {rows.map((p) => (
          <div className="card" key={p.id}>
            <h3>{p.name}</h3>
            <p className="muted">
              {p.tone || "no tone"} · {p.audience || "no audience"}
            </p>
            <p>{p.description}</p>
          </div>
        ))}
      </div>
    </>
  );
}
