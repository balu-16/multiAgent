import type { ChatMessageEvent } from "@/types/chat";
import { Avatar } from "./Avatar";

export function MessageBubble({ message, grouped, reply }: { message: ChatMessageEvent; grouped: boolean; reply?: ChatMessageEvent }) {
  const time = new Date(message.timestamp);
  return <article className={`message-row ${grouped ? "grouped" : "first-in-group"}`} id={`message-${message.id}`} aria-label={`${message.sender}: ${message.text}`}>
    <div className="message-avatar">{!grouped && <Avatar name={message.sender} color={message.color} size={38} />}</div>
    <div className="message-content">
      {!grouped && <div className="message-byline"><span className="message-sender" style={{ color: message.color }}>{message.sender}</span><time dateTime={message.timestamp}>{Number.isFinite(time.getTime()) ? time.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : ""}</time></div>}
      <div className="message-bubble">
        {message.reply_to && <div className="reply-pill"><span className="reply-glyph" aria-hidden="true">↳</span><span>{reply ? <><strong>{reply.sender}</strong><span>{reply.text}</span></> : "Earlier message"}</span></div>}
        <p>{message.text.replaceAll("|||", "").trim()}</p>
      </div>
    </div>
  </article>;
}
