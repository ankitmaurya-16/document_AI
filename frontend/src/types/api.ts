// Domain types shared across the frontend. These are the contract with the
// Flask v1 API — keep in sync with backend/docs/API.md and backend/schemas.py.

export type Role = "user" | "assistant" | "system";

export interface User {
  _id: string;
  email: string;
  name: string;
  credits: number;
}

export interface Source {
  source: string;
  text?: string;
  score?: number;
}

export interface Message {
  role: Role;
  content: string;
  timestamp: number;
  files?: string[];
  sources?: string[] | Source[];
  rating?: -1 | 0 | 1;
  isImage?: boolean;
  isPublished?: boolean;
}

export interface Chat {
  _id: string;
  userId: string;
  name: string;
  messages: Message[];
  createdAt: string;
  updatedAt: string;
}

export interface Document {
  _id: string;
  filename: string;
  size: number;
  uploadedAt: string;
}

export interface Plan {
  _id: string;
  name: string;
  price: number;
  credits: number;
  features: string[];
}

// ---- API response envelopes ----

export interface AuthResponse {
  token: string;
  user: User;
}

export interface VerifyResponse {
  user: User;
}

export interface ChatsResponse {
  chats: Chat[];
}

export interface ChatResponse {
  chat: Chat;
}

export interface DocumentsResponse {
  documents: Document[];
}

export interface PlansResponse {
  plans: Plan[];
}

export interface CheckoutResponse {
  url?: string;
  error?: string;
}

export interface ChatReply {
  response: string;
  sources?: string[] | Source[];
  chatId?: string;
  credits_exhausted?: boolean;
  error?: string;
}

// ---- SSE frames emitted by /api/v1/chat (streaming variants) ----
// See backend/routes/v1/rag_chat.py for the canonical shapes.

export type SSEFrame =
  | { type: "meta"; chatId: string; sources?: string[] | Source[] }
  | { type: "delta"; content: string }
  | { type: "done"; chatId: string }
  | { type: "error"; error: string; code?: string };

// ---- Feedback ----

export interface FeedbackPayload {
  chatId: string;
  messageTimestamp: number;
  rating: -1 | 0 | 1;
  comment?: string | null;
}
