"use client";

import { useState } from "react";

export default function PracticePage() {
  const [count, setCount] = useState(0);

  return (
    <div className="max-w-3xl mx-auto px-4 py-16">
      <h1 className="text-3xl font-bold text-slate-800 dark:text-slate-100">
        按钮交互实验室
      </h1>
      <p className="mt-4 text-slate-600 dark:text-slate-400">
        我点了 {count} 次
      </p>
      <button
        onClick={() => setCount(count + 1)}
        className="mt-6 px-5 py-2 rounded-xl bg-sky-500 text-white hover:bg-sky-600 transition-colors"
      >
        点我 +1
      </button>
    </div>
  );
}