import React, { useState, useRef } from "react";
import ChatBox from "./components/ChatBox";

function App() {
  const [messages, setMessages] = useState([]);
  const [activities, setActivities] = useState([]);
  // useRef so the accumulated steps are always current inside the async closure
  const stepsRef = useRef([]);

  const handleSubmit = async (query, setLoading) => {
    setMessages((prev) => [...prev, { role: "user", text: query }]);
    setActivities([]);
    stepsRef.current = [];
    setLoading(true);

    try {
      const res = await fetch("/ask/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Server error");
      }

      if (!res.body) {
        throw new Error("Streaming not supported by this browser.");
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) continue;

          let event;
          try {
            event = JSON.parse(trimmed);
          } catch (_) {
            continue;
          }

          if (event.type === "status") {
            stepsRef.current = [...stepsRef.current, event.message];
            setActivities([...stepsRef.current]);
          }

          if (event.type === "error") {
            throw new Error(event.message || "Streaming request failed.");
          }

          if (event.type === "final") {
            // Attach the captured steps to the message so they persist after loading ends
            setMessages((prev) => [
              ...prev,
              {
                role: "assistant",
                text: event.response,
                latency_ms: event.latency_ms,
                steps: stepsRef.current,
              },
            ]);
          }
        }
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "error", text: `Error: ${err.message}` },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={styles.app}>
      <header style={styles.header}>
        <h1 style={styles.title}>⚙️ GenAI Ops Copilot</h1>
        <p style={styles.subtitle}>
          Enterprise-grade AI-powered root cause analysis for data pipelines
        </p>
      </header>

      <main style={styles.main}>
        <ChatBox messages={messages} activities={activities} onSubmit={handleSubmit} />
      </main>
    </div>
  );
}

const styles = {
  app: {
    fontFamily: "'Segoe UI', Roboto, sans-serif",
    backgroundColor: "#0f1117",
    minHeight: "100vh",
    color: "#e2e8f0",
    display: "flex",
    flexDirection: "column",
  },
  header: {
    padding: "24px 32px",
    borderBottom: "1px solid #2d3748",
    backgroundColor: "#1a1f2e",
  },
  title: {
    margin: 0,
    fontSize: "1.75rem",
    fontWeight: 700,
    color: "#63b3ed",
  },
  subtitle: {
    margin: "6px 0 0",
    fontSize: "0.9rem",
    color: "#718096",
  },
  main: {
    flex: 1,
    display: "flex",
    justifyContent: "center",
    padding: "32px 16px",
  },
};

export default App;
