"use client";

import { useState } from "react";

export function Avatar({ name, color = "#4A6B5D", size = 44, className = "" }: { name: string; color?: string; size?: number; className?: string }) {
  const [failedSeed, setFailedSeed] = useState<string | null>(null);
  return <span className={`avatar ${className}`} style={{ width: size, height: size, backgroundColor: `${color}18`, color }} aria-hidden="true">
    {failedSeed === name ? name.slice(0, 1).toUpperCase() : <img
      src={`https://api.dicebear.com/9.x/notionists/svg?seed=${encodeURIComponent(name)}&backgroundColor=efe9dc`}
      alt="" width={size} height={size} loading="lazy" referrerPolicy="no-referrer"
      onError={() => setFailedSeed(name)}
    />}
  </span>;
}
