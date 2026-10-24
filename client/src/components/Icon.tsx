import type { CSSProperties } from "react";

type IconName = "arrow" | "back" | "spark" | "chat" | "eye" | "check" | "archive" | "logout" | "refresh" | "lock" | "chevron" | "close";
const paths: Record<IconName, React.ReactNode> = {
  arrow: <><path d="M4 12h15M13 5l7 7-7 7" /></>,
  back: <><path d="M20 12H5m6-7-7 7 7 7" /></>,
  spark: <><path d="m12 3 2.4 6.6L21 12l-6.6 2.4L12 21l-2.4-6.6L3 12l6.6-2.4L12 3Z" /><path d="m20 2 .6 1.4L22 4l-1.4.6L20 6l-.6-1.4L18 4l1.4-.6L20 2Z" /></>,
  chat: <><path d="M20 11.5a7.5 7.5 0 0 1-7.5 7.5H5l-4 3v-9.5A9.5 9.5 0 0 1 10.5 3H12a8 8 0 0 1 8 8.5Z" /><path d="M7 10h7m-7 4h4" /></>,
  eye: <><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /></>,
  check: <path d="m5 12 4 4L19 6" />,
  archive: <><path d="M4 8v12h16V8M3 3h18v5H3zM9 12h6" /></>,
  logout: <><path d="M9 4H4v16h5m5-15 7 7-7 7m7-7H9" /></>,
  refresh: <><path d="M20 8a8 8 0 1 0 0 8M20 3v6h-6" /></>,
  lock: <><rect x="5" y="10" width="14" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2" /></>,
  chevron: <path d="m9 5 7 7-7 7" />,
  close: <path d="m6 6 12 12M6 18 18 6" />,
};

export function Icon({ name, size = 20, style, className = "" }: { name: IconName; size?: number; style?: CSSProperties; className?: string }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" style={style} className={className} aria-hidden="true">{paths[name]}</svg>;
}
