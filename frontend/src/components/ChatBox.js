import React, { useState, useRef, useEffect } from "react";

/**
 * ChatBox — renders the conversation history and the query input form.
 *
 * Props:
 *   messages  — array of { role: 'user'|'assistant'|'error', text, latency_ms? }
 *   activities — array of live activity status strings
 *   onSubmit  — (query: string, setLoading: fn) => void
 */
function ChatBox({ messages, activities, onSubmit }) {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);

  // Auto-scroll to latest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const handleSubmit = (e) => {
    e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed || loading) return;
    setQuery("");
    onSubmit(trimmed, setLoading);
  };

  const handleKeyDown = (e) => {
    // Ctrl+Enter or Cmd+Enter submits
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      handleSubmit(e);
    }
  };

  return (
    <div style={styles.container}>
      {/* Message history */}
      <div style={styles.history}>
        {messages.length === 0 && (
          <div style={styles.placeholder}>
            Ask about pipeline failures, data quality issues, or active incidents.
          </div>
        )}

        {messages.map((msg, idx) => (
          <MessageBubble key={idx} message={msg} />
        ))}

        {loading && (
          <div style={{ ...styles.bubble, ...styles.assistantBubble, opacity: 0.9 }}>
            <span style={styles.roleLabel}>Copilot Live</span>
            <p style={styles.messageText}>Working in real time:</p>
            <ul style={styles.activityList}>
              {activities.length === 0 && <li style={styles.activityItem}>Starting...</li>}
              {activities.map((activity, idx) => (
                <li key={`${activity}-${idx}`} style={styles.activityItem}>
                  {activity}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <form onSubmit={handleSubmit} style={styles.form}>
        <textarea
          style={styles.textarea}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask a question… (Ctrl+Enter to submit)"
          rows={3}
          disabled={loading}
        />
        <button
          type="submit"
          style={{
            ...styles.button,
            ...(loading || !query.trim() ? styles.buttonDisabled : {}),
          }}
          disabled={loading || !query.trim()}
        >
          {loading ? "Thinking…" : "Ask Copilot"}
        </button>
      </form>
    </div>
  );
}

function MessageBubble({ message }) {
  const isUser = message.role === "user";
  const isError = message.role === "error";

  const bubbleStyle = isUser
    ? { ...styles.bubble, ...styles.userBubble }
    : isError
    ? { ...styles.bubble, ...styles.errorBubble }
    : { ...styles.bubble, ...styles.assistantBubble };

  const label = isUser ? "You" : isError ? "Error" : "Copilot";

  return (
    <div style={bubbleStyle}>
      <span style={styles.roleLabel}>{label}</span>

      {/* Persistent tool-call timeline shown for assistant messages */}
      {!isUser && !isError && message.steps && message.steps.length > 0 && (
        <StepTimeline steps={message.steps} />
      )}

      {isUser || isError ? (
        <pre style={styles.messageText}>{message.text}</pre>
      ) : (
        <FormattedResponse text={message.text} />
      )}
      {message.latency_ms !== undefined && (
        <span style={styles.latency}>⚡ {message.latency_ms} ms</span>
      )}
    </div>
  );
}

/** Maps raw status messages to human-friendly labels with icons */
function friendlyStep(msg) {
  // Check action-level patterns FIRST (before tool-name patterns) to avoid
  // "Executed mcp.get_case_by_id successfully" matching the tool-name rule
  if (/Starting agentic/i.test(msg))         return { icon: "🚀", text: "Initialising agentic planner" };
  if (/Loaded \d+ MCP tools/i.test(msg))     return { icon: "🗂️", text: msg };
  if (/Planning step/i.test(msg))            return { icon: "🧠", text: msg };
  if (/Planner decided/i.test(msg))          return { icon: "💡", text: "Enough evidence collected — generating answer" };
  if (/Synthesizing final/i.test(msg))       return { icon: "✍️", text: "Synthesising final response" };
  if (/invalid JSON/i.test(msg))             return { icon: "⚠️", text: "Planner parse error — retrying" };
  if (/Planner returned unsupported/i.test(msg)) return { icon: "⚠️", text: "Planner action error — continuing" };

  // "Selected tool:" → show the domain icon, no redundant 🔧
  if (/Selected tool:/i.test(msg)) {
    const toolMatch = msg.match(/Selected tool:\s*(mcp\.\w+)/i);
    const tool = toolMatch ? toolMatch[1] : "";
    const SELECTED_LABELS = {
      "mcp.get_pact_cases":             { icon: "📋", text: "Querying PACT — all exception cases" },
      "mcp.get_case_by_id":             { icon: "📁", text: "Querying PACT — case details" },
      "mcp.get_tlm_breaks":             { icon: "📊", text: "Querying TLM SmartStream — reconciliation breaks" },
      "mcp.get_tlm_break_by_id":        { icon: "🔗", text: "Querying TLM SmartStream — specific break" },
      "mcp.get_ge_results":             { icon: "🧪", text: "Querying Great Expectations — validation results" },
      "mcp.get_ge_suite_result":        { icon: "🧪", text: "Querying Great Expectations — suite result" },
      "mcp.get_notification_templates": { icon: "📧", text: "Querying Notification Server — email templates" },
      "mcp.send_notification":          { icon: "📤", text: "Querying Notification Server — sending alert" },
    };
    return SELECTED_LABELS[tool] || { icon: "🔧", text: "Selecting tool: " + tool };
  }

  // "Executed … successfully" → show a checkmark
  if (/Executed .+ successfully/i.test(msg)) {
    const execMatch = msg.match(/Executed (.+?) successfully/i);
    const tool = execMatch ? execMatch[1] : "";
    const EXEC_LABELS = {
      "mcp.get_pact_cases":             "PACT cases fetched",
      "mcp.get_case_by_id":             "PACT case details received",
      "mcp.get_tlm_breaks":             "TLM breaks received",
      "mcp.get_tlm_break_by_id":        "TLM break record received",
      "mcp.get_ge_results":             "GE validation results received",
      "mcp.get_ge_suite_result":        "GE suite result received",
      "mcp.get_notification_templates": "Notification templates received",
      "mcp.send_notification":          "Notification email sent",
    };
    return { icon: "✅", text: EXEC_LABELS[tool] || ("Done: " + tool) };
  }

  if (/Tool execution failed/i.test(msg)) return { icon: "❌", text: msg };

  return { icon: "▸", text: msg };
}

function StepTimeline({ steps }) {
  // Filter out low-value noise
  const filtered = steps.filter(
    (s) => !/^Planning step \d/i.test(s) && !/^Loaded \d+ MCP/i.test(s)
  );
  if (filtered.length === 0) return null;

  return (
    <div style={styles.timeline}>
      <span style={styles.timelineLabel}>🔎 Investigation trace</span>
      <ol style={styles.timelineList}>
        {filtered.map((step, idx) => {
          const { icon, text } = friendlyStep(step);
          return (
            <li key={idx} style={styles.timelineItem}>
              {icon} {text}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

/**
 * Renders assistant response with styled Issue / RCA / Resolution sections.
 * Falls back to plain <pre> if none of the section headers are found.
 */
function FormattedResponse({ text }) {
  // Section header patterns produced by both prompts
  const sectionRe = /(🔴\s*ISSUE|🔍\s*ROOT CAUSE ANALYSIS[^━\n]*|✅\s*RESOLUTION)/;

  if (!sectionRe.test(text)) {
    return <pre style={styles.messageText}>{text}</pre>;
  }

  // Split on the ━ divider lines and collect chunks
  const chunks = text.split(/━{3,}/).map((s) => s.trim()).filter(Boolean);

  const sectionMeta = {
    ISSUE: { icon: "🔴", color: "#fc8181", bg: "rgba(252,129,129,0.08)" },
    "ROOT CAUSE": { icon: "🔍", color: "#f6e05e", bg: "rgba(246,224,94,0.07)" },
    RESOLUTION: { icon: "✅", color: "#68d391", bg: "rgba(104,211,145,0.08)" },
  };

  const rendered = [];
  let i = 0;
  while (i < chunks.length) {
    const chunk = chunks[i];
    // Detect if this chunk IS a header label
    const headerMatch = chunk.match(/^(🔴\s*ISSUE|🔍\s*ROOT CAUSE[^\n]*|✅\s*RESOLUTION)/i);
    if (headerMatch) {
      const header = headerMatch[1].toUpperCase();
      const key = Object.keys(sectionMeta).find((k) => header.includes(k)) || "ISSUE";
      const meta = sectionMeta[key];
      const body = chunks[i + 1] || "";
      i += 2;
      rendered.push(
        <div key={key} style={{ ...styles.section, borderLeft: `3px solid ${meta.color}`, background: meta.bg }}>
          <span style={{ ...styles.sectionHeader, color: meta.color }}>
            {meta.icon} {key === "ROOT CAUSE" ? "ROOT CAUSE ANALYSIS (RCA)" : key}
          </span>
          <pre style={styles.sectionBody}>{body.trim()}</pre>
        </div>
      );
    } else {
      // Plain text outside sections
      if (chunk) {
        rendered.push(<pre key={`plain-${i}`} style={styles.messageText}>{chunk}</pre>);
      }
      i += 1;
    }
  }

  return <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>{rendered}</div>;
}

const styles = {
  container: {
    width: "100%",
    maxWidth: "900px",
    display: "flex",
    flexDirection: "column",
    gap: "16px",
  },
  history: {
    flex: 1,
    minHeight: "400px",
    maxHeight: "60vh",
    overflowY: "auto",
    display: "flex",
    flexDirection: "column",
    gap: "12px",
    padding: "8px",
    backgroundColor: "#1a1f2e",
    borderRadius: "12px",
    border: "1px solid #2d3748",
  },
  placeholder: {
    color: "#4a5568",
    fontSize: "0.95rem",
    textAlign: "center",
    paddingTop: "60px",
  },
  bubble: {
    padding: "14px 18px",
    borderRadius: "10px",
    maxWidth: "90%",
  },
  userBubble: {
    backgroundColor: "#2b4a7a",
    alignSelf: "flex-end",
    borderBottomRightRadius: "2px",
  },
  assistantBubble: {
    backgroundColor: "#1e2d40",
    alignSelf: "flex-start",
    borderBottomLeftRadius: "2px",
    border: "1px solid #2d3748",
  },
  errorBubble: {
    backgroundColor: "#4a1515",
    alignSelf: "flex-start",
    border: "1px solid #742a2a",
  },
  roleLabel: {
    display: "block",
    fontSize: "0.72rem",
    fontWeight: 600,
    color: "#718096",
    marginBottom: "6px",
    textTransform: "uppercase",
    letterSpacing: "0.05em",
  },
  messageText: {
    margin: 0,
    fontSize: "0.93rem",
    lineHeight: 1.65,
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
    color: "#e2e8f0",
    fontFamily: "inherit",
  },
  latency: {
    display: "block",
    marginTop: "8px",
    fontSize: "0.72rem",
    color: "#4a5568",
  },
  timeline: {
    marginBottom: "14px",
    padding: "10px 14px",
    borderRadius: "8px",
    backgroundColor: "rgba(45,55,72,0.6)",
    border: "1px solid #2d3748",
  },
  timelineLabel: {
    display: "block",
    fontSize: "0.72rem",
    fontWeight: 700,
    color: "#718096",
    letterSpacing: "0.06em",
    textTransform: "uppercase",
    marginBottom: "8px",
  },
  timelineList: {
    margin: 0,
    padding: 0,
    listStyle: "none",
    display: "flex",
    flexDirection: "column",
    gap: "5px",
  },
  timelineItem: {
    fontSize: "0.85rem",
    color: "#a0aec0",
    lineHeight: 1.6,
    paddingLeft: "4px",
  },
  section: {
    padding: "12px 16px",
    borderRadius: "8px",
    marginBottom: "2px",
  },
  sectionHeader: {
    display: "block",
    fontSize: "0.8rem",
    fontWeight: 700,
    letterSpacing: "0.07em",
    textTransform: "uppercase",
    marginBottom: "8px",
  },
  sectionBody: {
    margin: 0,
    fontSize: "0.93rem",
    lineHeight: 1.7,
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
    color: "#e2e8f0",
    fontFamily: "inherit",
  },
  activityList: {
    margin: "8px 0 0",
    paddingLeft: "18px",
  },
  activityItem: {
    color: "#cbd5e0",
    fontSize: "0.88rem",
    lineHeight: 1.6,
    marginBottom: "4px",
  },
  form: {
    display: "flex",
    flexDirection: "column",
    gap: "10px",
  },
  textarea: {
    width: "100%",
    padding: "14px",
    borderRadius: "10px",
    border: "1px solid #2d3748",
    backgroundColor: "#1a1f2e",
    color: "#e2e8f0",
    fontSize: "0.95rem",
    resize: "vertical",
    outline: "none",
    boxSizing: "border-box",
    fontFamily: "inherit",
  },
  button: {
    alignSelf: "flex-end",
    padding: "10px 28px",
    borderRadius: "8px",
    border: "none",
    backgroundColor: "#3182ce",
    color: "#fff",
    fontSize: "0.95rem",
    fontWeight: 600,
    cursor: "pointer",
    transition: "background-color 0.2s",
  },
  buttonDisabled: {
    backgroundColor: "#2d3748",
    cursor: "not-allowed",
    color: "#718096",
  },
};

export default ChatBox;
