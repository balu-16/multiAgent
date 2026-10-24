import { z } from "zod";

export const personaSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  role_in_group: z.string().min(1),
  vibe_and_style: z.string().min(1),
  expertise: z.array(z.string()),
  stance_on_topic: z.string().min(1),
  talkativeness: z.number().min(0).max(1),
  color: z.string().regex(/^#[0-9a-f]{6}$/i),
});

export const chatMessageSchema = z.object({
  type: z.literal("chat_message"),
  id: z.string().min(1),
  sender_id: z.string().min(1),
  sender: z.string(),
  color: z.string().regex(/^#[0-9a-f]{6}$/i),
  text: z.string(),
  reply_to: z.string().nullable(),
  count: z.number().int().positive(),
  max_messages: z.number().int().positive(),
  timestamp: z.string(),
  seq: z.number().int().nonnegative(),
});

export const systemEventSchema = z.object({
  type: z.literal("system_event"),
  id: z.string().min(1),
  text: z.string(),
  reason: z.enum(["agent_left", "max_reached", "room_error"]),
  agent_id: z.string().nullable(),
  timestamp: z.string(),
  seq: z.number().int().nonnegative(),
});

export const roomStatusSchema = z.enum(["running", "completed", "failed"]);
export const archiveStatusSchema = z.enum(["pending", "saved"]);
export const roomEventSchema = z.discriminatedUnion("type", [
  chatMessageSchema,
  systemEventSchema,
  z.object({
    type: z.literal("typing"),
    sender_id: z.string(),
    sender: z.string(),
    is_typing: z.boolean(),
    seq: z.number().int().nonnegative(),
  }),
  z.object({
    type: z.literal("archive_status"),
    status: archiveStatusSchema,
    seq: z.number().int().nonnegative(),
  }),
  z.object({
    type: z.literal("history_sync"),
    messages: z.array(chatMessageSchema),
    system_events: z.array(systemEventSchema),
    count: z.number().int().nonnegative(),
    max_messages: z.number().int().positive(),
    status: roomStatusSchema,
    online_agent_ids: z.array(z.string()),
    typing_agent_ids: z.array(z.string()),
    last_seq: z.number().int().nonnegative(),
    archive_status: archiveStatusSchema.nullable(),
  }),
]);

export const userSchema = z.object({ id: z.string(), email: z.string() });
export const authResponseSchema = z.object({ user: userSchema });
export const personasResponseSchema = z.object({ personas: z.array(personaSchema).min(2).max(6) });
export const startResponseSchema = z.object({ room_id: z.string(), status: z.literal("started") });

export const chatSummarySchema = z.object({
  id: z.string(),
  topic: z.string(),
  message_count: z.number().int().nonnegative(),
  max_messages: z.number().int().positive(),
  created_at: z.string(),
  ended_at: z.string(),
  reason: z.string(),
});
export const archiveListSchema = z.object({
  chats: z.array(chatSummarySchema),
  next_cursor: z.string().nullable(),
});
export const archivedChatSchema = chatSummarySchema.extend({
  personas: z.array(personaSchema),
  messages: z.array(chatMessageSchema),
  system_events: z.array(systemEventSchema),
});
export const archiveDetailSchema = z.object({ chat: archivedChatSchema });

export type AgentPersona = z.infer<typeof personaSchema>;
export type ChatMessageEvent = z.infer<typeof chatMessageSchema>;
export type SystemEvent = z.infer<typeof systemEventSchema>;
export type RoomEvent = z.infer<typeof roomEventSchema>;
export type HistorySync = Extract<RoomEvent, { type: "history_sync" }>;
export type User = z.infer<typeof userSchema>;
export type ArchivedChat = z.infer<typeof archivedChatSchema>;
export type ChatSummary = z.infer<typeof chatSummarySchema>;
export type RoomStatus = z.infer<typeof roomStatusSchema>;
export type ArchiveStatus = z.infer<typeof archiveStatusSchema> | null;
export type ConnectionStatus = "connecting" | "connected" | "reconnecting" | "disconnected" | "finished";

export interface TopicConfig {
  topic: string;
  num_agents: number;
  max_messages: number;
}
