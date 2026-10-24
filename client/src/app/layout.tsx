import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Backchannel — Good company. Interesting takes.",
  description: "Pick a topic, meet your AI friend group, and take a front row seat to a conversation with a life of its own.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
