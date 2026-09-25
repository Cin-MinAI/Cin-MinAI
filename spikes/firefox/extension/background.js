// Cin-MinAI Firefox extension (M0 spike, SPEC §7): context menus, native messaging, relay to the sidebar.
// Page content is only read when the user asks (menu click → activeTab), and is capped with a notice.

const HOST = "org.cinminai.assistant";
const LIMIT = 12000; // characters of page/selection text per request (~3.5K tokens; fits an 8K context)

let port = null;
let transcript = [];      // what the sidebar shows; kept here so it survives closing the sidebar
let status = { state: "connecting", model: "" };
let pending = null;       // context the user shared and hasn't asked about yet

function post(msg) {
  if (!port) connect();
  port.postMessage(msg);
}

function connect() {
  port = browser.runtime.connectNative(HOST);
  port.onMessage.addListener((m) => {
    if (m.type === "status") status = m;
    else transcript.push(m);
    if (transcript.length > 2000) transcript.splice(0, transcript.length - 2000);
    broadcast({ type: "host", message: m });
  });
  port.onDisconnect.addListener((p) => {
    const why = (p.error && p.error.message) || "the assistant helper stopped";
    status = { state: "offline", model: "", error: why };
    broadcast({ type: "host", message: status });
    port = null;
  });
}

function broadcast(msg) {
  browser.runtime.sendMessage(msg).catch(() => {}); // no sidebar open: fine
}

function cap(text) {
  const t = text || "";
  return t.length > LIMIT ? { text: t.slice(0, LIMIT), truncated: true, total: t.length }
                          : { text: t, truncated: false, total: t.length };
}

browser.runtime.onInstalled.addListener(() => {
  browser.menus.create({ id: "ask-selection", title: "Ask Cin-MinAI about “%s”", contexts: ["selection"] });
  browser.menus.create({ id: "ask-page", title: "Ask Cin-MinAI about this page", contexts: ["page"] });
});

browser.menus.onClicked.addListener(async (info, tab) => {
  browser.sidebarAction.open(); // must happen synchronously in the user's click
  let text = "";
  if (info.menuItemId === "ask-selection") {
    // menus give a shortened selection; read the full one from the page (activeTab from this click).
    try {
      const [r] = await browser.scripting.executeScript({
        target: { tabId: tab.id }, func: () => String(window.getSelection()) });
      text = r.result || info.selectionText;
    } catch (e) {
      text = info.selectionText;
    }
  } else {
    try {
      const [r] = await browser.scripting.executeScript({
        target: { tabId: tab.id }, func: () => document.body ? document.body.innerText : "" });
      text = r.result || "";
    } catch (e) {
      text = "";
    }
  }
  const c = cap(text);
  pending = { kind: info.menuItemId === "ask-selection" ? "selection" : "page",
              title: tab.title || "", url: tab.url || "", ...c };
  broadcast({ type: "pending", pending });
});

browser.runtime.onMessage.addListener((msg) => {
  if (msg.type === "hello") {
    if (!port) connect();
    post({ type: "status" });
    return Promise.resolve({ transcript, status, pending });
  }
  if (msg.type === "ask") {
    const context = msg.useContext ? pending : null;
    pending = null;
    transcript.push({ type: "user", text: msg.question, context: context && {
      kind: context.kind, title: context.title, truncated: context.truncated, total: context.total } });
    post({ type: "ask", question: msg.question, context });
    return Promise.resolve({ ok: true });
  }
  if (msg.type === "drop-context") {
    pending = null;
    return Promise.resolve({ ok: true });
  }
  if (msg.type === "cancel") {
    post({ type: "cancel" });
    return Promise.resolve({ ok: true });
  }
});
