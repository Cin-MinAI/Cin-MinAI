// SPDX-License-Identifier: GPL-3.0-or-later
// Cin-MinAI in Firefox (D14, D78): when the person asks the assistant about "this video", the assistant asks here,
// and this reads the YouTube video open in the front tab — its title, length, transcript (the panel the page shows
// under "Show transcript") and the storyboard (YouTube's own preview pictures). Only YouTube (Ian, 2026-10-04:
// "stick with known trustworthy sources"), only when asked, and nothing but the video's words and pictures.
// Ads aren't in either, so the summary skips them.

const HOST = "org.cinminai.assistant";
let port = null;

function connect() {
  port = browser.runtime.connectNative(HOST);
  port.onMessage.addListener(async (m) => {
    if (m.type === "current_video") {
      let out;
      try {
        out = await currentVideo();
      } catch (e) {
        out = { error: "read", detail: String(e) };
      }
      port.postMessage({ type: "video", req: m.req, ...out });
    }
  });
  port.onDisconnect.addListener(() => {
    port = null;
    setTimeout(connect, 5000); // the helper restarts with the assistant
  });
}

async function currentVideo() {
  const [tab] = await browser.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab || !tab.url || !/^https:\/\/www\.youtube\.com\/watch\?/.test(tab.url)) {
    return { error: "no_video" }; // not a YouTube video (or a site this can't read: tab.url is hidden then)
  }
  const [r] = await browser.scripting.executeScript({ target: { tabId: tab.id }, world: "MAIN", func: readPage });
  return { url: tab.url, ...(r && r.result ? r.result : { error: "read" }) };
}

// Runs in the YouTube page. Reads what the page shows; opens the transcript panel if it's closed (and closes it
// again), the same as clicking "Show transcript".
async function readPage() {
  const sleep = (ms) => new Promise((ok) => setTimeout(ok, ms));
  const player = document.getElementById("movie_player");
  const pr = player && player.getPlayerResponse ? player.getPlayerResponse() : window.ytInitialPlayerResponse;
  if (!pr || !pr.videoDetails) return { error: "read" };
  const details = pr.videoDetails;
  const sb = (pr.storyboards && pr.storyboards.playerStoryboardSpecRenderer) || {};

  const SEG = "ytd-transcript-segment-renderer, transcript-segment-view-model";
  const segments = () => Array.from(document.querySelectorAll(SEG));
  let opened = false;
  if (!segments().length) {
    const button = document.querySelector("ytd-video-description-transcript-section-renderer button")
      || Array.from(document.querySelectorAll("button")).find((b) => /transcript/i.test(b.getAttribute("aria-label") || b.innerText || ""));
    if (button) {
      button.click();
      opened = true;
      for (let i = 0; i < 40 && !segments().length; i++) await sleep(250);
    }
  }
  const lines = [];
  for (const seg of segments()) {
    const parts = (seg.innerText || "").split("\n").map((s) => s.trim()).filter(Boolean);
    const at = parts.findIndex((p) => /^\d+(:\d\d){1,2}$/.test(p));
    if (at < 0) continue;
    const text = parts.filter((_, i) => i !== at).join(" ");
    if (!text) continue;
    const t = parts[at].split(":").reduce((a, b) => a * 60 + Number(b), 0);
    lines.push([t, text]);
  }
  if (opened) {
    const panel = document.querySelector('[target-id="engagement-panel-searchable-transcript"]');
    const close = panel && panel.querySelector("#visibility-button button, button[aria-label*='lose']");
    if (close) close.click();
  }
  return {
    id: details.videoId, title: details.title, author: details.author,
    length: Number(details.lengthSeconds) || 0, live: !!details.isLiveContent && !Number(details.lengthSeconds),
    storyboard: sb.spec || "", transcript: lines,
  };
}

connect();
