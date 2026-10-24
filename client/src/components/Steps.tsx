export function Steps({ stage }: { stage: "CONFIG" | "ROSTER" | "LIVE" }) {
  const active = ["CONFIG", "ROSTER", "LIVE"].indexOf(stage);
  return <nav className="workflow-steps" aria-label="Conversation progress"><ol>
    {["Set the scene", "Meet the group", "Listen in"].map((label, index) => <li key={label} className={index === active ? "current" : index < active ? "done" : ""} aria-current={index === active ? "step" : undefined}><span className="step-number">{index < active ? "✓" : `0${index + 1}`}</span><span>{label}</span>{index < 2 && <span className="step-line" />}</li>)}
  </ol></nav>;
}
