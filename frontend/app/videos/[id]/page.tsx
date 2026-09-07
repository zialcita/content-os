"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type Clip, type Video } from "@/lib/api";

export default function VideoDetailPage() {
  const params = useParams<{ id: string }>();
  const [video, setVideo] = useState<Video | null>(null);
  const [script, setScript] = useState("");
  const [clips, setClips] = useState<Clip[]>([]);
  const [error, setError] = useState("");

  async function load() {
    const v = await api<Video>(`/v1/videos/${params.id}`);
    setVideo(v);
    setScript(v.script_draft);
    const c = await api<Clip[]>(`/v1/videos/${params.id}/clips`);
    setClips(c);
  }

  useEffect(() => {
    load().catch((err) => setError(String(err)));
  }, [params.id]);

  async function run(path: string, method = "POST", body?: unknown) {
    setError("");
    try {
      await api(`/v1/videos/${params.id}${path}`, {
        method,
        body: body ? JSON.stringify(body) : undefined,
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    }
  }

  if (!video) return <p className="muted">Loading…</p>;

  return (
    <>
      <h2>{video.title}</h2>
      <p className="lead">
        <span className={`status ${video.status}`}>{video.status}</span>
        {video.published_url && (
          <>
            {" "}
            · <a href={video.published_url}>{video.published_url}</a>
          </>
        )}
      </p>
      {error && <p className="error">{error}</p>}
      <div className="row" style={{ marginBottom: 16 }}>
        <button onClick={() => void run("/script", "PATCH", { script })}>Save script</button>
        <button className="primary" onClick={() => void run("/approve-script")}>
          Approve script
        </button>
        <button onClick={() => void run("/resolve-broll")}>Resolve B-roll</button>
        <button onClick={() => void run("/assemble")}>Assemble</button>
        <button className="ok" onClick={() => void run("/approve")}>
          Approve cut
        </button>
        <button className="warn" onClick={() => void run("/publish")}>
          Publish
        </button>
      </div>
      <form className="stack" onSubmit={(e) => e.preventDefault()}>
        <textarea value={script} onChange={(e) => setScript(e.target.value)} />
      </form>
      <h3 style={{ marginTop: 24 }}>Scenes</h3>
      <div className="grid">
        {video.scenes.map((s) => (
          <div className="card" key={s.id}>
            <h3>Scene {s.idx + 1}</h3>
            <p>{s.script_text}</p>
            <p className="muted">B-roll: {s.visual_direction || "—"}</p>
          </div>
        ))}
      </div>
      {clips.length > 0 && (
        <>
          <h3 style={{ marginTop: 24 }}>Clips</h3>
          <ul>
            {clips.map((c) => (
              <li key={c.id}>
                {c.title} ({c.start_s}s–{c.end_s}s)
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}
