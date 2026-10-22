// SPDX-License-Identifier: GPL-3.0-or-later
// Cin-MinAI assistant panel icon (SPEC §5.2), from the M0 desktop-surface spike (GO 2026-09-24).
// A click opens or closes the sidebar; the icon and tooltip show the assistant's state, and WEB or CLOUD
// beside it shows Cin-MinAI reaching out (D35, D28), or OFFLINE in offline mode (D28); the right-click
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
// D28 (Ian, 2026-10-16): a log the person switches on — off by default; a record kept unasked "comes off as spying"
const LOG_SWITCH = GLib.get_user_config_dir() + "/cinminai/internet-log-on";
const LOG_FILE = GLib.get_user_state_dir() + "/cinminai/internet-log.txt";
const LOG_WORDS = {
    en: ["Log every internet session on this computer", "Open the internet log"],
    es: ["Registrar cada sesión de internet en este ordenador", "Abrir el registro de internet"],
    pt: ["Registrar cada sessão de internet neste computador", "Abrir o registro de internet"],
    fr: ["Journaliser chaque session internet sur cet ordinateur", "Ouvrir le journal internet"],
    de: ["Jede Internetsitzung auf diesem Computer protokollieren", "Internetprotokoll öffnen"],
    ja: ["このコンピューターのインターネット接続をすべて記録する", "インターネットの記録を開く"],
};

// D28: keep this computer offline — the switch and the one button for updates (cinminai-offline does the work)
const OFFLINE_SWITCH = GLib.get_user_config_dir() + "/cinminai/offline-on";
const OFFLINE = "/usr/bin/cinminai-offline";
const UPDATES = "/usr/bin/cinminai-updates";  // D29: the Updates window, online or offline (it goes online itself)
const OFFLINE_WORDS = {
    en: ["Keep this computer offline", "Go online to install updates", "OFFLINE", "Offline: Wi-Fi and cable are off",
         "Updates…"],
    es: ["Mantener este equipo sin conexión", "Conectarse para instalar actualizaciones", "SIN RED",
         "Sin conexión: el wifi y el cable están apagados", "Actualizaciones…"],
    pt: ["Manter este computador offline", "Conectar para instalar atualizações", "OFFLINE",
         "Offline: o Wi-Fi e o cabo estão desligados", "Atualizações…"],
    fr: ["Garder cet ordinateur hors ligne", "Se connecter pour installer les mises à jour", "HORS LIGNE",
         "Hors ligne : le Wi-Fi et le câble sont coupés", "Mises à jour…"],
    de: ["Diesen Computer offline halten", "Für Updates online gehen", "OFFLINE", "Offline: WLAN und Kabel sind aus",
         "Updates…"],
    ja: ["このコンピューターをオフラインに保つ", "オンラインにしてアップデートを入れる", "オフライン",
         "オフライン：Wi-Fiも有線も切れています", "アップデート…"],
};

function offline() {
    return GLib.file_test(OFFLINE_SWITCH, GLib.FileTest.EXISTS);
}

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
        // the internet log: off until the person switches it on; "Open" shows the plain text file
        const words = LOG_WORDS[LANG] || LOG_WORDS.en;
        this.logSwitch = new PopupMenu.PopupSwitchMenuItem(words[0], GLib.file_test(LOG_SWITCH, GLib.FileTest.EXISTS));
        this.logSwitch.connect("toggled", (item, on) => {
            try {
                if (on) {
                    GLib.mkdir_with_parents(GLib.path_get_dirname(LOG_SWITCH), 0o700);
                    GLib.file_set_contents(LOG_SWITCH, "on\n");
                } else {
                    Gio.File.new_for_path(LOG_SWITCH).delete(null);
                }
            } catch (e) { global.logError(`cinminai applet: ${e}`); }
            this.logOpen.actor.visible = on;
        });
        ctx.addMenuItem(this.logSwitch, 7);
        this.logOpen = new PopupMenu.PopupMenuItem(words[1]);
        this.logOpen.connect("activate", () => {
            GLib.mkdir_with_parents(GLib.path_get_dirname(LOG_FILE), 0o700);
            if (!GLib.file_test(LOG_FILE, GLib.FileTest.EXISTS)) GLib.file_set_contents(LOG_FILE, "");
            Util.spawn(["xdg-open", LOG_FILE]);
        });
        this.logOpen.actor.visible = GLib.file_test(LOG_SWITCH, GLib.FileTest.EXISTS);
        ctx.addMenuItem(this.logOpen, 8);
        // offline mode: the whole computer, switched here; going online for updates is the one button beside it
        const off = OFFLINE_WORDS[LANG] || OFFLINE_WORDS.en;
        this.offlineSwitch = new PopupMenu.PopupSwitchMenuItem(off[0], offline());
        this.offlineSwitch.connect("toggled", (item, on) => {
            Util.spawn([OFFLINE, on ? "on" : "off"]);
            this.updatesItem.label.set_text(on ? off[1] : off[4]);
        });
        ctx.addMenuItem(this.offlineSwitch, 9);
        // always there (findable): "Updates…", or "Go online to install updates" while offline; the same window
        this.updatesItem = new PopupMenu.PopupMenuItem(offline() ? off[1] : off[4]);
        this.updatesItem.connect("activate", () => Util.spawn([UPDATES]));
        ctx.addMenuItem(this.updatesItem, 10);
        ctx.addMenuItem(new PopupMenu.PopupSeparatorMenuItem(), 11);

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
        // security updates in offline mode: a reminder at most once a month (cinminai-offline decides when)
        Util.spawn([OFFLINE, "remind"]);
        this.remindTimer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 6 * 3600, () => {
            Util.spawn([OFFLINE, "remind"]);
            return true;
        });
    }

    on_applet_removed_from_panel() {
        if (this.reachTimer) GLib.source_remove(this.reachTimer);
        if (this.remindTimer) GLib.source_remove(this.remindTimer);
    }

    showReach() {
        const now = reaching();
        const off = offline();
        const key = now.map(m => m.kind + m.to).join("|") + (off ? "|offline" : "");
        if (key === this.reachKey) return;
        this.reachKey = key;
        this.reach = now;
        this.offline = off;
        this.offlineSwitch.setToggleState(off);  // switched elsewhere (cinminai-offline) shows here too
        const said = OFFLINE_WORDS[LANG] || OFFLINE_WORDS.en;
        this.updatesItem.label.set_text(off ? said[1] : said[4]);
        this.set_applet_label(now.length ? (now[0].kind === "cloud" ? "CLOUD" : "WEB")
                              : off ? (OFFLINE_WORDS[LANG] || OFFLINE_WORDS.en)[2] : "");
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
            : this.offline ? (OFFLINE_WORDS[LANG] || OFFLINE_WORDS.en)[3] : r.local;
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
