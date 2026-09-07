"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type Video } from "@/lib/api";

export default function ReviewPage() {
  const [videos, setVideos] = useState<Video[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Video[]>("/v1/videos")
      .then(setVideos)
      .catch((err) => setError(String(err)));
  }, []);

  const queue = videos.filter((v) => v.status === "script_ready" || v.status === "in_review");

  async function act(id: string, path: string) {
    try {
      await api(`/v1/videos/${id}${path}`, { method: "POST" });
      setVideos(await api<Video[]>("/v1/videos"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    }
  }

  return (
    <>
      <h2>Review</h2>
      <p className="lead">Human checkpoints: script approve and final-cut approve.</p>
      {error && <p className="error">{error}</p>}
      <div className="grid">
        {queue.map((v) => (
          <div className="card" key={v.id}>
            <h3>{v.title}</h3>
            <p>
              <span className={`status ${v.status}`}>{v.status}</span>
            </p>
            <div className="row">
              <Link href={`/videos/${v.id}`}>Open</Link>
              {v.status === "script_ready" && (
                <button className="primary" onClick={() => void act(v.id, "/approve-script")}>
                  Approve script
                </button>
              )}
              {v.status === "in_review" && (
                <button className="ok" onClick={() => void act(v.id, "/approve")}>
                  Approve cut
                </button>
              )}
            </div>
          </div>
        ))}
        {queue.length === 0 && <p className="muted">Nothing waiting on a human.</p>}
      </div>
    </>
  );
}
