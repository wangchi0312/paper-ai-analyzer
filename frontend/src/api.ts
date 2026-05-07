import type { AgentResponse, AppConfig, Job, MemoryWriteResponse, PendingAction, Recommendation } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<T>;
}

export function getConfig(): Promise<AppConfig> {
  return request<AppConfig>("/api/config");
}

export function saveConfig(config: Partial<AppConfig> & Record<string, unknown>): Promise<AppConfig> {
  return request<AppConfig>("/api/config", {
    method: "POST",
    body: JSON.stringify(config),
  });
}

export function sendMessage(message: string): Promise<AgentResponse> {
  return request<AgentResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}

export async function uploadPdf(file: File): Promise<AgentResponse> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${API_BASE}/api/upload`, {
    method: "POST",
    body: form,
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<AgentResponse>;
}

export function startJob(action: PendingAction): Promise<Job> {
  return request<Job>("/api/jobs", {
    method: "POST",
    body: JSON.stringify({ action }),
  });
}

export function cancelJob(jobId: string): Promise<Job> {
  return request<Job>(`/api/jobs/${jobId}/cancel`, {
    method: "POST",
  });
}

export function openJobEvents(jobId: string): EventSource {
  return new EventSource(`${API_BASE}/api/jobs/${jobId}/events`);
}

export function rememberRecommendationInterest(
  item: Recommendation,
  memoryType: "positive_interest" | "negative_interest",
): Promise<MemoryWriteResponse> {
  const label = memoryType === "positive_interest" ? "我对这类论文主题感兴趣" : "这类论文与我的研究方向不相关";
  return request<MemoryWriteResponse>("/api/memory/interest", {
    method: "POST",
    body: JSON.stringify({
      text: `${label}：${item.title}\n\n摘要：${item.abstract || "未获取到摘要"}`,
      memory_type: memoryType,
      evidence_source: "wos_feedback",
      weight: 0.9,
      confidence: 0.85,
      metadata: {
        title: item.title,
        doi: item.doi,
        score: item.score,
        source: "wos_recommendation",
      },
    }),
  });
}

export function rememberRecommendationPaper(item: Recommendation): Promise<MemoryWriteResponse> {
  return request<MemoryWriteResponse>("/api/memory/paper", {
    method: "POST",
    body: JSON.stringify({
      text: `${item.title}\n\n${item.abstract || ""}\n\n推荐理由：${item.reason}`,
      metadata: {
        title: item.title,
        doi: item.doi,
        authors: item.authors,
        venue: item.venue,
        source: "wos_recommendation",
        score: item.score,
      },
    }),
  });
}
