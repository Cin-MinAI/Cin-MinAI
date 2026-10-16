// SPDX-License-Identifier: GPL-3.0-or-later
// Cin-MinAI assistant panel icon (SPEC §5.2), from the M0 desktop-surface spike (GO 2026-09-24).
// A click opens or closes the sidebar; the icon and tooltip show the assistant's state, and WEB or CLOUD
// beside it shows Cin-MinAI reaching out (D35, D28); the right-click
// menu adds the model line, "Open assistant" and "New conversation". It never starts the daemon by
// itself: the daemon starts at login (its autostart) or when the sidebar opens.

const Applet = imports.ui.applet;
const PopupMenu = imports.ui.popupMenu;
const Util = imports.misc.util;
const Gio = imports.gi.Gio;

const BUS_NAME = "org.cinminai.Assistant1";
const OBJ_PATH = "/org/cinminai/Assistant1";
const IFACE_XML = `
<node>
  <interface name="org.cinminai.Assistant1">
    <method name="Reset"/>
    <property name="State" type="s" access="read"/>
    <property name="Model" type="s" access="read"/>
  </interface>
</node>`;
const AssistantProxy = Gio.DBusProxy.makeProxyWrapper(IFACE_XML);
const SIDEBAR = "/usr/bin/cinminai-sidebar";
const GLib = imports.gi.GLib;
// update 5's menu entry in the six v1 languages (D25); the older entries are still English
const STANDING = { en: "Standing tasks", es: "Tareas permanentes", pt: "Tarefas permanentes",
                   fr: "Tâches permanentes", de: "Daueraufgaben", ja: "定期タスク" };
const REQUESTS = { en: "Requests", es: "Peticiones", pt: "Pedidos", fr: "Demandes", de: "Anfragen",
                   ja: "リクエスト" };
const MODELS = { en: "Models", es: "Modelos", pt: "Modelos", fr: "Modèles", de: "Modelle", ja: "モデル" };
const LANG = (GLib.get_language_names()[0] || "en").slice(0, 2);
// D35 / D28: where Cin-MinAI is reaching now — beside the icon while something is out, nothing when all is local
const REACH = {
    en: { local: "Everything stays on this computer", web: "On the internet now", cloud: "Sending to a cloud model now" },
    es: { local: "Todo se queda en este ordenador", web: "En internet ahora", cloud: "Enviando a un modelo en la nube" },
    pt: { local: "Tudo fica neste computador", web: "Na internet agora", cloud: "Enviando a um modelo na nuvem" },
    fr: { local: "Tout reste sur cet ordinateur", web: "Sur Internet en ce moment", cloud: "Envoi à un modèle dans le cloud" },
    de: { local: "Alles bleibt auf diesem Computer", web: "Gerade im Internet", cloud: "Sendet an ein Cloud-Modell" },
    ja: { local: "すべてこのコンピューターの中にあります", web: "インターネットに接続中", cloud: "クラウドのモデルに送信中" },
};
const REACH_DIR = GLib.get_user_runtime_dir() + "/cinminai/reach";

function reaching() {
    // the marks in force (inference/reach.py): [{kind, to, until}], cloud first
    const out = [];
    const dir = Gio.File.new_for_path(REACH_DIR);
    let files;
    try {
        files = dir.enumerate_children("standard::name", Gio.FileQueryInfoFlags.NONE, null);
    } catch (e) {
        return out;
    }
    const now = Date.now() / 1000;
    let info;
    while ((info = files.next_file(null)) !== null) {
        const name = info.get_name();
        if (!name.endsWith(".json")) continue;
        try {
            const [ok, bytes] = GLib.file_get_contents(REACH_DIR + "/" + name);
            const mark = JSON.parse(imports.byteArray.toString(bytes));
            if (ok && mark.until > now) out.push(mark);
        } catch (e) { /* half-written: next time */ }
    }
    files.close(null);
    return out.sort((a, b) => (a.kind === "cloud" ? 0 : 1) - (b.kind === "cloud" ? 0 : 1));
}

// State property -> [symbolic icon, words]. Placeholder icons from the theme until Ian's artwork.
const STATES = {
    idle: ["user-available-symbolic", "Ready"],
    thinking: ["emblem-synchronizing-symbolic", "Answering…"],
    loading: ["emblem-synchronizing-symbolic", "Getting ready…"],
    off: ["user-away-symbolic", "Resting (starts when you ask)"],
    error: ["dialog-error-symbolic", "Not available"],
    offline: ["user-offline-symbolic", "Not running (opens when you click)"],
};

class CinMinAIApplet extends Applet.TextIconApplet {
    constructor(metadata, orientation, panelHeight, instanceId) {
        super(orientation, panelHeight, instanceId);
        this.stateItem = new PopupMenu.PopupMenuItem("", { reactive: false });
        this.modelItem = new PopupMenu.PopupMenuItem("", { reactive: false });
        const ctx = this._applet_context_menu;
        ctx.addMenuItem(this.stateItem, 0);
        ctx.addMenuItem(this.modelItem, 1);
        const open = new PopupMenu.PopupMenuItem("Open assistant");
        open.connect("activate", () => Util.spawn([SIDEBAR, "--show"]));
        ctx.addMenuItem(open, 2);
        const reset = new PopupMenu.PopupMenuItem("New conversation");
        reset.connect("activate", () => {
            if (this.proxy && this.proxy.g_name_owner) this.proxy.ResetRemote(() => {});
        });
        ctx.addMenuItem(reset, 3);
        // D88: the person's standing tasks, where they look for them (Ian, 2026-10-07: "If I can't find it they
        // might not either")
        const standing = new PopupMenu.PopupMenuItem(STANDING[LANG] || STANDING.en);
        standing.connect("activate", () => Util.spawn([SIDEBAR, "--standing"]));
        ctx.addMenuItem(standing, 4);
        // turn tokens (SPEC §22.4): what was asked, who's working on what, Stop
        const requests = new PopupMenu.PopupMenuItem(REQUESTS[LANG] || REQUESTS.en);
        requests.connect("activate", () => Util.spawn([SIDEBAR, "--requests"]));
        ctx.addMenuItem(requests, 5);
        // which model does which job (SPEC §22.3)
        const models = new PopupMenu.PopupMenuItem(MODELS[LANG] || MODELS.en);
        models.connect("activate", () => Util.spawn([SIDEBAR, "--models"]));
        ctx.addMenuItem(models, 6);
        ctx.addMenuItem(new PopupMenu.PopupSeparatorMenuItem(), 7);

        this.proxy = null;
        new AssistantProxy(Gio.DBus.session, BUS_NAME, OBJ_PATH, (proxy, error) => {
            if (error) { global.logError(`cinminai applet: ${error}`); this.refresh(); return; }
            this.proxy = proxy;
            proxy.connect("g-properties-changed", () => this.refresh());
            proxy.connect("notify::g-name-owner", () => this.refresh());
            this.refresh();
        }, null, Gio.DBusProxyFlags.DO_NOT_AUTO_START);
        this.refresh();
        this.reach = [];
        this.reachTimer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 2, () => { this.showReach(); return true; });
    }

    on_applet_removed_from_panel() {
        if (this.reachTimer) GLib.source_remove(this.reachTimer);
    }

    showReach() {
        const now = reaching();
        const key = now.map(m => m.kind + m.to).join("|");
        if (key === this.reachKey) return;
        this.reachKey = key;
        this.reach = now;
        this.set_applet_label(now.length ? (now[0].kind === "cloud" ? "CLOUD" : "WEB") : "");
        this.refresh();
    }

    state() {
        if (!this.proxy || !this.proxy.g_name_owner) return "offline";
        return this.proxy.State || "offline";
    }

    refresh() {
        const state = this.state();
        const [icon, words] = STATES[state] || STATES.error;
        this.set_applet_icon_symbolic_name(icon);
        const r = REACH[LANG] || REACH.en;
        const reach = (this.reach || []).length
            ? `${this.reach[0].kind === "cloud" ? r.cloud : r.web}: ${[...new Set(this.reach.map(m => m.to))].join(", ")}`
            : r.local;
        this.set_applet_tooltip(`Assistant: ${words}\n${reach}\nClick to open or close (Super+A)`);
        this.stateItem.label.set_text(`Assistant: ${words}`);
        const model = state !== "offline" && this.proxy ? this.proxy.Model : "";
        this.modelItem.label.set_text(model ? model : "Model: not loaded");
    }

    on_applet_clicked() {
        Util.spawn([SIDEBAR, "--flip"]);
    }
}

function main(metadata, orientation, panelHeight, instanceId) {
    return new CinMinAIApplet(metadata, orientation, panelHeight, instanceId);
}
