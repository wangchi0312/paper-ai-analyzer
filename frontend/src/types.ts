export type PendingAction = {
  tool_name: string;
  args: Record<string, unknown>;
  summary: string;
  requires_confirmation: boolean;
  action_id: string;
  created_at: string;
};

export type AgentResponse = {
  message: string;
  pending_action?: PendingAction | null;
  tool_result?: ToolResult | null;
  uploaded_path?: string;
};

export type ToolResult = {
  tool_name: string;
  ok: boolean;
  message: string;
  data: Record<string, unknown>;
  error?: string | null;
  display_message?: string;
};

export type Job = {
  job_id: string;
  action: PendingAction;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  logs: string[];
  result?: ToolResult | null;
  error?: string | null;
  cancel_requested?: boolean;
};

export type Recommendation = {
  title: string;
  doi: string;
  authors: string;
  venue: string;
  abstract: string;
  link: string;
  publisher_link: string;
  wos_summary_url: string;
  score: number;
  reason: string;
  manual_pdf_advice: string;
  missing?: { doi?: boolean; abstract?: boolean };
};

export type ChatMessage = {
  id: string;
  role: "assistant" | "user";
  content: string;
  pendingAction?: PendingAction | null;
  job?: Job | null;
  recommendations?: Recommendation[];
  uploadedPath?: string;
};

export type AppConfig = {
  email_address: string;
  email_provider: string;
  email_auth_code_configured: boolean;
  llm_provider: string;
  llm_api_key_configured: boolean;
  llm_base_url: string;
  llm_model: string;
  llm_temperature: string;
  research_topic: string;
  full_text_source: string;
  wos_use_browser: boolean;
  wos_max_emails: number;
  wos_browser_max_pages: number;
  memory?: {
    backend: string;
    paper_corpus: number;
    interest_memory: number;
  };
};
