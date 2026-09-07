"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type Persona, type Video } from "@/lib/api";

export default function VideosPage() {
  const [videos, setVideos] = useState<Video[]>([]);
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [title, setTitle] = useState("");
  const [topic, setTopic] = useState("");
  const [personaId, setPersonaId] = useState("");
  const [error, setError] = useState("");

  async function refresh() {
    const [v, p] = await Promise.all([
      api<Video[]>("/v1/videos"),
      api<Persona[]>("/v1/personas"),
    ]);
    setVideos(v);
    setPersonas(p);
  }

  useEffect(() => {
    refresh().catch((err) => setError(String(err)));
  }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api<Video>("/v1/videos", {
        method: "POST",
        body: JSON.stringify({
          title,
          topic,
          persona_id: personaId || null,
        }),
      });
      setTitle("");
      setTopic("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    }
  }

  return (
    <>
      <h2>Videos</h2>
      <p className="lead">YouTube pillar pipeline. Create a video to generate a script.</p>
      <form className="card stack" onSubmit={(e) => void create(e)} style={{ marginBottom: 20 }}>
        <input required value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title" />
        <input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="Topic / angle" />
        <select value={personaId} onChange={(e) => setPersonaId(e.target.value)}>
          <option value="">No persona</option>
          {personas.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <button className="primary" type="submit">
          Create video
        </button>
      </form>
      {error && <p className="error">{error}</p>}
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Title</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {videos.map((v) => (
              <tr key={v.id}>
                <td>{v.title}</td>
                <td>
                  <span className={`status ${v.status}`}>{v.status}</span>
                </td>
                <td>
                  <Link href={`/videos/${v.id}`}>Open</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {videos.length === 0 && <p className="muted">No videos yet.</p>}
      </div>
    </>
  );
}
