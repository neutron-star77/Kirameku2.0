"use client";

import dynamic from "next/dynamic";

const FloatingPlayer = dynamic(() => import("@/components/music/FloatingPlayer"), { ssr: false });

export default function ClientWidgets() {
  return (
    <>
      <FloatingPlayer />
    </>
  );
}
