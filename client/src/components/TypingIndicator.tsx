import type { AgentPersona } from "@/types/chat";

export function TypingIndicator({ personas, typingIds }: { personas: AgentPersona[]; typingIds: string[] }) {
  const names = personas.filter((persona) => typingIds.includes(persona.id)).map((persona) => persona.name);
  if (!names.length) return <div className="typing-footer" aria-live="polite"><span className="quiet-label">A LITTLE SPACE BETWEEN THE TAKES</span></div>;
  const label = new Intl.ListFormat("en", { style: "long", type: "conjunction" }).format(names);
  return <div className="typing-footer is-typing" role="status"><span className="typing-dots"><i /><i /><i /></span><span>{label} {names.length === 1 ? "is" : "are"} typing…</span></div>;
}
