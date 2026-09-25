// Sidebar panel: the conversation, what's shared, and the input.

const chat = document.getElementById("chat");
const statusEl = document.getElementById("status");
const input = document.getElementById("input");
const stop = document.getElementById("stop");
const shared = document.getElementById("shared");
const sharedText = document.getElementById("shared-text");
let pending = null;
let answering = null; // element receiving the current answer

function line(cls, text) {
  const d = document.createElement("div");
  d.className = cls;
  d.textContent = text;
  chat.appendChild(d);
  chat.scrollTop = chat.scrollHeight;
  return d;
}

function describe(c) {
  const what = c.kind === "selection" ? "Selected text" : "This page";
  const size = `${c.text ? c.text.length : c.total} characters`;
  return c.truncated
    ? `${what} from “${c.title}” — only the first ${size} of ${c.total} will be shared (too long)`
    : `${what} from “${c.title}” (${size}) will be shared with your next question`;
}

function showPending(p) {
  pending = p;
  shared.hidden = !p;
  if (p) {
    sharedText.textContent = describe(p);
    shared.classList.toggle("warn", !!p.truncated);
    input.placeholder = p.kind === "selection" ? "Ask about the selection… (Enter: explain it)" : "Ask about this page… (Enter: summarize it)";
    input.focus();
  } else {
    input.placeholder = "Ask…";
  }
}

function showStatus(s) {
  if (s.state === "offline") {
    statusEl.textContent = `● offline — ${s.error || "assistant not running"}`;
  } else {
    statusEl.textContent = `● ${s.state || "?"}   ${s.model || ""}   LOCAL`;
  }
  stop.hidden = s.state !== "thinking";
}

function render(m) {
  if (m.type === "status" || m.state) return showStatus(m);
  if (m.type === "user") {
    line("you", `You: ${m.text}`);
    if (m.context) line("note", `with ${m.context.kind} from “${m.context.title}”${m.context.truncated ? " (shortened)" : ""}`);
    answering = line("answer", "");
  } else if (m.type === "token") {
    if (!answering) answering = line("answer", "");
    answering.textContent += m.text;
    chat.scrollTop = chat.scrollHeight;
  } else if (m.type === "done") {
    answering = null;
  } else if (m.type === "error") {
    line("error", `Couldn't get an answer: ${m.message}`);
    answering = null;
  }
}

browser.runtime.onMessage.addListener((msg) => {
  if (msg.type === "host") render(msg.message);
  if (msg.type === "pending") showPending(msg.pending);
});

input.addEventListener("keydown", async (e) => {
  if (e.key !== "Enter" || e.shiftKey) return;
  e.preventDefault();
  let q = input.value.trim();
  if (!q && pending) q = pending.kind === "selection" ? "Explain this." : "Summarize this page.";
  if (!q) return;
  input.value = "";
  const useContext = !!pending;
  render({ type: "user", text: q, context: pending && { kind: pending.kind, title: pending.title, truncated: pending.truncated } });
  showPending(null);
  await browser.runtime.sendMessage({ type: "ask", question: q, useContext });
});

document.getElementById("drop").addEventListener("click", async () => {
  await browser.runtime.sendMessage({ type: "drop-context" });
  showPending(null);
});

stop.addEventListener("click", () => browser.runtime.sendMessage({ type: "cancel" }));

browser.runtime.sendMessage({ type: "hello" }).then((r) => {
  for (const m of r.transcript) render(m);
  showStatus(r.status);
  showPending(r.pending);
});
