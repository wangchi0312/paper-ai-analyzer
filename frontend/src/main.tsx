import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Bot,
  Check,
  Copy,
  ExternalLink,
  FilePlus2,
  FileText,
  Loader2,
  Mail,
  Paperclip,
  Plus,
  Save,
  Send,
  Settings2,
  Square,
  X,
} from "lucide-react";
import { cancelJob, getConfig, openJobEvents, saveConfig, sendMessage, startJob, uploadPdf } from "./api";
import type { AgentResponse, AppConfig, ChatMessage, Job, PendingAction, Recommendation, ToolResult } from "./types";
import "./styles.css";

const initialMessage: ChatMessage = {
  id: crypto.randomUUID(),
  role: "assistant",
  content:
    "你好，我是你的本地学术助手。你可以直接提问，也可以在下方附加 PDF。涉及 WoS 批量筛选、长期记忆或报告生成时，我会先说明计划，再等你确认。",
};

const capabilityHints = [
  "快速解读上传论文",
  "筛选 WoS Alert 候选论文",
  "结合历史论文给出建议",
  "整理阶段性研究笔记",
];

function App() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([initialMessage]);
  const [input, setInput] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);
  const [sending, setSending] = useState(false);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    getConfig().then(setConfig).catch((error) => appendAssistant(`读取配置失败：${error.message}`));
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const currentConversationLabel = useMemo(() => {
    const firstUser = messages.find((item) => item.role === "user");
    return firstUser ? firstUser.content.slice(0, 18) || "当前对话" : "新对话";
  }, [messages]);

  function appendAssistant(content: string, extra?: Partial<ChatMessage>) {
    setMessages((items) => [...items, { id: crypto.randomUUID(), role: "assistant", content, ...extra }]);
  }

  function appendUser(content: string) {
    setMessages((items) => [...items, { id: crypto.randomUUID(), role: "user", content }]);
  }

  function resetConversation() {
    setMessages([initialMessage]);
    setInput("");
    setFile(null);
    setActiveJobId(null);
  }

  async function handleSend() {
    const text = input.trim();
    if (!text && !file) return;
    setSending(true);
    try {
      setInput("");
      if (file) {
        appendUser(`上传 PDF：${file.name}${text ? `\n\n附言：${text}` : ""}`);
        const response = await uploadPdf(file);
        addAgentResponse(response);
        setFile(null);
        return;
      }
      appendUser(text);
      const response = await sendMessage(text);
      addAgentResponse(response);
    } catch (error) {
      appendAssistant(`发送失败：${(error as Error).message}`);
    } finally {
      setSending(false);
    }
  }

  function addAgentResponse(response: AgentResponse) {
    const recommendations = extractRecommendations(response.tool_result ?? undefined);
    appendAssistant(response.message, {
      pendingAction: response.pending_action ?? null,
      recommendations,
      uploadedPath: response.uploaded_path,
    });
  }

  async function confirmAction(messageId: string, action: PendingAction) {
    setMessages((items) =>
      items.map((item) =>
        item.id === messageId
          ? { ...item, pendingAction: null, content: `${item.content}\n\n已开始执行。` }
          : item,
      ),
    );
    try {
      const job = await startJob(action);
      setActiveJobId(job.job_id);
      setMessages((items) => items.map((item) => (item.id === messageId ? { ...item, job } : item)));
      streamJob(messageId, job.job_id);
    } catch (error) {
      appendAssistant(`启动任务失败：${(error as Error).message}`);
    }
  }

  async function handleCancelJob(messageId: string, jobId: string) {
    try {
      const job = await cancelJob(jobId);
      setMessages((items) =>
        items.map((item) =>
          item.id === messageId && item.job
            ? { ...item, job: { ...item.job, ...job, status: "running", cancel_requested: true } }
            : item,
        ),
      );
    } catch (error) {
      appendAssistant(`停止任务失败：${(error as Error).message}`);
    }
  }

  function streamJob(messageId: string, jobId: string) {
    const source = openJobEvents(jobId);
    source.addEventListener("status", (event) => {
      const data = JSON.parse((event as MessageEvent).data) as { status: Job["status"] | "cancelling" };
      setMessages((items) => updateJobStatus(items, messageId, data.status));
    });
    source.addEventListener("log", (event) => {
      const data = JSON.parse((event as MessageEvent).data) as { message: string };
      setMessages((items) => updateJobLogs(items, messageId, data.message));
    });
    source.addEventListener("result", (event) => {
      const result = JSON.parse((event as MessageEvent).data) as ToolResult;
      setMessages((items) => attachJobResult(items, messageId, result));
    });
    source.addEventListener("done", () => {
      setActiveJobId((current) => (current === jobId ? null : current));
      source.close();
    });
    source.onerror = () => {
      setMessages((items) => updateJobLogs(items, messageId, "日志连接已断开，请检查任务状态。"));
      setActiveJobId((current) => (current === jobId ? null : current));
      source.close();
    };
  }

  async function handleSaveConfig(next: Record<string, unknown>) {
    setSaving(true);
    try {
      const saved = await saveConfig(next);
      setConfig(saved);
      appendAssistant("配置已保存到本地 .env。密钥只保存在你的机器上，不会提交到 Git。");
    } catch (error) {
      appendAssistant(`配置保存失败：${(error as Error).message}`);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="app-shell">
      <aside className="chat-rail">
        <div className="rail-brand">
          <Bot size={20} />
          <div>
            <strong>学术助手</strong>
            <span>对话式工作台</span>
          </div>
        </div>
        <button className="primary-rail-button" type="button" onClick={resetConversation}>
          <Plus size={16} />
          新对话
        </button>
        <section className="rail-section">
          <h3>当前会话</h3>
          <button className="conversation-chip active" type="button">
            {currentConversationLabel}
          </button>
        </section>
        <section className="rail-section">
          <h3>你可以这样用</h3>
          <ul className="capability-list">
            {capabilityHints.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <h1>对话</h1>
            <p>不自动下载全文。WoS 只负责筛选候选，PDF 由你手动下载后再上传深读。</p>
          </div>
          {activeJobId && (
            <div className="topbar-status">
              <Loader2 className="spin" size={16} />
              <span>后台任务执行中</span>
            </div>
          )}
        </header>

        <section className="messages">
          {messages.map((message) => (
            <MessageView
              key={message.id}
              message={message}
              onConfirm={confirmAction}
              onCancelJob={handleCancelJob}
            />
          ))}
          <div ref={bottomRef} />
        </section>

        <footer className="composer">
          {file && (
            <div className="attachment">
              <div className="attachment-info">
                <FileText size={16} />
                <span>{file.name}</span>
              </div>
              <button type="button" onClick={() => setFile(null)} aria-label="移除附件">
                <X size={16} />
              </button>
            </div>
          )}
          <div className="composer-panel">
            <div className="composer-row">
              <label className="icon-button" title="上传 PDF">
                <Paperclip size={18} />
                <input
                  type="file"
                  accept="application/pdf,.pdf"
                  hidden
                  onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                />
              </label>
              <textarea
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder="输入消息，或附加 PDF 后发送"
                rows={1}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    handleSend();
                  }
                }}
              />
              <button className="send-button" type="button" onClick={handleSend} disabled={sending}>
                {sending ? <Loader2 className="spin" size={18} /> : <Send size={18} />}
              </button>
            </div>
            <div className="composer-hint">
              <span>上传 PDF 后，我会先给出待确认动作，再开始解读。</span>
              {file ? <span>当前已附加 1 个 PDF</span> : <span>支持回车发送，Shift+Enter 换行</span>}
            </div>
          </div>
        </footer>
      </main>

      <aside className="settings-panel-wrap">
        {config && <SettingsPanel config={config} saving={saving} onSave={handleSaveConfig} />}
      </aside>
    </div>
  );
}

function SettingsPanel({
  config,
  saving,
  onSave,
}: {
  config: AppConfig;
  saving: boolean;
  onSave: (data: Record<string, unknown>) => void;
}) {
  const [draft, setDraft] = useState<Record<string, unknown>>({
    email_address: config.email_address,
    email_provider: config.email_provider,
    email_auth_code: "",
    llm_provider: config.llm_provider,
    llm_api_key: "",
    llm_base_url: config.llm_base_url,
    llm_model: config.llm_model,
    llm_temperature: config.llm_temperature,
    research_topic: config.research_topic,
    wos_use_browser: config.wos_use_browser,
    wos_max_emails: config.wos_max_emails,
    wos_browser_max_pages: config.wos_browser_max_pages,
  });

  useEffect(() => {
    setDraft({
      email_address: config.email_address,
      email_provider: config.email_provider,
      email_auth_code: "",
      llm_provider: config.llm_provider,
      llm_api_key: "",
      llm_base_url: config.llm_base_url,
      llm_model: config.llm_model,
      llm_temperature: config.llm_temperature,
      research_topic: config.research_topic,
      wos_use_browser: config.wos_use_browser,
      wos_max_emails: config.wos_max_emails,
      wos_browser_max_pages: config.wos_browser_max_pages,
    });
  }, [config]);

  const update = (key: string, value: unknown) => setDraft((data) => ({ ...data, [key]: value }));

  return (
    <div className="settings-panel">
      <div className="settings-header">
        <div>
          <h2>配置</h2>
          <p>邮箱、模型和 WoS 范围都在这里设置。</p>
        </div>
        <Settings2 size={18} />
      </div>

      <div className="memory-stats">
        <div>
          <span>记忆后端</span>
          <strong>{config.memory?.backend ?? "unknown"}</strong>
        </div>
        <div>
          <span>论文记忆</span>
          <strong>{config.memory?.paper_corpus ?? 0}</strong>
        </div>
        <div>
          <span>兴趣记忆</span>
          <strong>{config.memory?.interest_memory ?? 0}</strong>
        </div>
      </div>

      <section className="settings-group">
        <h3><Mail size={16} /> 邮箱</h3>
        <label>
          <span>默认邮箱</span>
          <input value={String(draft.email_address ?? "")} onChange={(e) => update("email_address", e.target.value)} placeholder="user@example.com" />
        </label>
        <label>
          <span>授权码</span>
          <input
            value={String(draft.email_auth_code ?? "")}
            onChange={(e) => update("email_auth_code", e.target.value)}
            placeholder={config.email_auth_code_configured ? "已配置授权码，留空表示不修改" : "输入邮箱授权码"}
            type="password"
          />
        </label>
      </section>

      <section className="settings-group">
        <h3><Bot size={16} /> LLM</h3>
        <label>
          <span>Provider</span>
          <select value={String(draft.llm_provider)} onChange={(e) => update("llm_provider", e.target.value)}>
            <option value="deepseek">DeepSeek</option>
            <option value="siliconflow">SiliconFlow</option>
            <option value="modelscope">ModelScope</option>
          </select>
        </label>
        <label>
          <span>API Key</span>
          <input
            value={String(draft.llm_api_key ?? "")}
            onChange={(e) => update("llm_api_key", e.target.value)}
            placeholder={config.llm_api_key_configured ? "已配置 API Key，留空表示不修改" : "输入 API Key"}
            type="password"
          />
        </label>
        <label>
          <span>Base URL</span>
          <input value={String(draft.llm_base_url ?? "")} onChange={(e) => update("llm_base_url", e.target.value)} placeholder="https://..." />
        </label>
        <label>
          <span>Model</span>
          <input value={String(draft.llm_model ?? "")} onChange={(e) => update("llm_model", e.target.value)} placeholder="模型名称" />
        </label>
      </section>

      <section className="settings-group">
        <h3><FilePlus2 size={16} /> WoS 筛选</h3>
        <label className="check-line">
          <input type="checkbox" checked={Boolean(draft.wos_use_browser)} onChange={(e) => update("wos_use_browser", e.target.checked)} />
          <div>
            <strong>使用浏览器补全摘要和 DOI</strong>
            <small>会尝试打开 WoS 完整结果页，补全摘要、DOI 和链接；速度更慢，但信息更完整。</small>
          </div>
        </label>
        <label>
          <span>最多读取多少封 WoS 邮件</span>
          <input
            type="number"
            value={Number(draft.wos_max_emails)}
            onChange={(e) => update("wos_max_emails", Number(e.target.value))}
            min={1}
            max={500}
          />
        </label>
        <label>
          <span>浏览器模式最多处理多少页 WoS 结果</span>
          <input
            type="number"
            value={Number(draft.wos_browser_max_pages)}
            onChange={(e) => update("wos_browser_max_pages", Number(e.target.value))}
            min={1}
            max={50}
          />
        </label>
      </section>

      <section className="settings-group">
        <h3>研究主题</h3>
        <label>
          <span>让 Agent 更懂你的方向</span>
          <textarea value={String(draft.research_topic ?? "")} onChange={(e) => update("research_topic", e.target.value)} rows={5} />
        </label>
      </section>

      <button className="save-button" type="button" onClick={() => onSave(draft)} disabled={saving}>
        {saving ? <Loader2 className="spin" size={16} /> : <Save size={16} />}
        保存到 .env
      </button>
      <p className="hint">保存后会写入本地 .env。该文件已被 Git 忽略，但仍然属于本机明文配置。</p>
    </div>
  );
}

function MessageView({
  message,
  onConfirm,
  onCancelJob,
}: {
  message: ChatMessage;
  onConfirm: (messageId: string, action: PendingAction) => void;
  onCancelJob: (messageId: string, jobId: string) => void;
}) {
  return (
    <article className={`message ${message.role}`}>
      <div className="bubble">
        <pre>{message.content}</pre>
        {message.uploadedPath && <div className="uploaded-path">文件已保存到：{message.uploadedPath}</div>}
        {message.pendingAction && (
          <div className="pending-card">
            <div className="pending-head">
              <strong>待确认动作</strong>
              <span>需要你点一下确认</span>
            </div>
            <p>{message.pendingAction.summary}</p>
            <button type="button" onClick={() => onConfirm(message.id, message.pendingAction!)}>
              <Check size={16} /> 确认执行
            </button>
          </div>
        )}
        {message.job && <JobLog messageId={message.id} job={message.job} onCancelJob={onCancelJob} />}
        {message.recommendations && <RecommendationList items={message.recommendations} />}
      </div>
    </article>
  );
}

function JobLog({
  messageId,
  job,
  onCancelJob,
}: {
  messageId: string;
  job: Job;
  onCancelJob: (messageId: string, jobId: string) => void;
}) {
  const running = job.status === "queued" || job.status === "running";
  return (
    <div className="job-log">
      <div className="job-title">
        <div className="job-title-left">
          <Loader2 className={running ? "spin" : ""} size={16} />
          <div>
            <strong>工作日志</strong>
            <span>{labelJobStatus(job)}</span>
          </div>
        </div>
        {running && (
          <button className="job-stop" type="button" onClick={() => onCancelJob(messageId, job.job_id)} disabled={Boolean(job.cancel_requested)}>
            <Square size={14} />
            {job.cancel_requested ? "停止中..." : "中断"}
          </button>
        )}
      </div>
      <div className="job-lines">
        {(job.logs ?? []).map((line, index) => (
          <code key={index}>{line}</code>
        ))}
      </div>
    </div>
  );
}

function RecommendationList({ items }: { items: Recommendation[] }) {
  if (!items.length) return null;
  return (
    <div className="recommendations">
      {items.map((item, index) => (
        <div className="recommendation" key={`${item.title}-${index}`}>
          <div className="rec-head">
            <div>
              <h3>{item.title}</h3>
              <div className="rec-meta">
                <span>{item.authors || "作者待补全"}</span>
                <span>{item.venue || "刊物待补全"}</span>
              </div>
            </div>
            <span className="score-badge">{Number.isFinite(item.score) ? item.score.toFixed(3) : "未评分"}</span>
          </div>

          <div className="field-row">
            <b>DOI</b>
            <span>{item.doi || "未获取到"}</span>
            {item.doi && (
              <button className="copy" type="button" onClick={() => navigator.clipboard.writeText(item.doi)}>
                <Copy size={14} />
                复制 DOI
              </button>
            )}
          </div>

          <div className="field-row stacked">
            <b>推荐理由</b>
            <span>{item.reason}</span>
          </div>

          <div className="field-row stacked">
            <b>摘要</b>
            <span>{item.abstract || "未获取到摘要，建议打开 WoS 记录确认。"}</span>
          </div>

          <div className="rec-actions">
            {item.wos_summary_url && (
              <a href={item.wos_summary_url} target="_blank" rel="noreferrer">
                <ExternalLink size={14} />
                打开 WoS
              </a>
            )}
            {item.publisher_link && (
              <a href={item.publisher_link} target="_blank" rel="noreferrer">
                <ExternalLink size={14} />
                打开期刊页
              </a>
            )}
            {item.link && !item.wos_summary_url && (
              <a href={item.link} target="_blank" rel="noreferrer">
                <ExternalLink size={14} />
                打开记录
              </a>
            )}
          </div>

          <p className="advice">{item.manual_pdf_advice}</p>
        </div>
      ))}
    </div>
  );
}

function extractRecommendations(result?: ToolResult | null): Recommendation[] {
  const raw = result?.data?.recommendations;
  return Array.isArray(raw) ? (raw as Recommendation[]) : [];
}

function updateJobStatus(items: ChatMessage[], messageId: string, status: Job["status"] | "cancelling"): ChatMessage[] {
  return items.map((item) => {
    if (item.id !== messageId || !item.job) return item;
    if (status === "cancelling") {
      return { ...item, job: { ...item.job, cancel_requested: true } };
    }
    return { ...item, job: { ...item.job, status } };
  });
}

function updateJobLogs(items: ChatMessage[], messageId: string, line: string): ChatMessage[] {
  return items.map((item) => {
    if (item.id !== messageId || !item.job) return item;
    return { ...item, job: { ...item.job, logs: [...(item.job.logs ?? []), line] } };
  });
}

function attachJobResult(items: ChatMessage[], messageId: string, result: ToolResult): ChatMessage[] {
  return items.map((item) => {
    if (item.id !== messageId || !item.job) return item;
    const nextStatus: Job["status"] = result.message === "任务已取消" ? "cancelled" : result.ok ? "completed" : "failed";
    return {
      ...item,
      content: `${item.content}\n\n${result.display_message ?? result.message}`,
      recommendations: extractRecommendations(result),
      job: { ...item.job, status: nextStatus, result, error: result.error ?? null },
    };
  });
}

function labelJobStatus(job: Job): string {
  if (job.status === "completed") return "已完成";
  if (job.status === "failed") return "失败";
  if (job.status === "cancelled") return "已取消";
  if (job.cancel_requested) return "正在停止";
  return "执行中";
}

createRoot(document.getElementById("root")!).render(<App />);
