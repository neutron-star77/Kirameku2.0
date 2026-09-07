"use client";

import { useEffect, useState } from "react";

type Chatter = {
  id: number;
  content: string;
  likes: number;
  mood: string;
  created_at: string;
};

export default function NotesPage() {
  const [chatters, setChatters] = useState<Chatter[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/chatters?status=published")
      .then((res) => res.json())
      .then((data) => {
        setChatters(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  return (
    <div className="max-w-3xl mx-auto px-4 py-16">
      <h1 className="text-5xl font-bold text-slate-800 dark:text-slate-100">
        说说
      </h1>
      <div className="mt-8 space-y-4">
        {loading ? (
          <p className="text-slate-400">加载中…</p>
        ) : chatters.length === 0 ? (
          <p className="text-slate-400">暂无说说</p>
        ) : (
          chatters.map((c) => (
            <div
              key={c.id}
              className="p-4 rounded-2xl bg-white/60 dark:bg-white/5 backdrop-blur border border-white/20"
            >
              <p className="text-slate-700 dark:text-slate-200">{c.content}</p>
              <div className="mt-2 flex items-center justify-between text-xs text-slate-400">
                <span>
                  {c.mood ? `【${c.mood}】` : ""}
                  {new Date(c.created_at).toLocaleString("zh-CN")}
                </span>
                <span>♥ {c.likes}</span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}