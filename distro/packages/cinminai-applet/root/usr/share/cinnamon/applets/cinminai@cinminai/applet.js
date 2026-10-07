// SPDX-License-Identifier: GPL-3.0-or-later
// Cin-MinAI assistant panel icon (SPEC §5.2), from the M0 desktop-surface spike (GO 2026-09-24).
// A click opens or closes the sidebar; the icon and tooltip show the assistant's state; the right-click
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
const LANG = (GLib.get_language_names()[0] || "en").slice(0, 2);

// State property -> [symbolic icon, words]. Placeholder icons from the theme until Ian's artwork.
const STATES = {
    idle: ["user-available-symbolic", "Ready"],
    thinking: ["emblem-synchronizing-symbolic", "Answering…"],
    loading: ["emblem-synchronizing-symbolic", "Getting ready…"],
    off: ["user-away-symbolic", "Resting (starts when you ask)"],
    error: ["dialog-error-symbolic", "Not available"],
    offline: ["user-offline-symbolic", "Not running (opens when you click)"],
};

class CinMinAIApplet extends Applet.IconApplet {
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
        ctx.addMenuItem(new PopupMenu.PopupSeparatorMenuItem(), 5);

        this.proxy = null;
        new AssistantProxy(Gio.DBus.session, BUS_NAME, OBJ_PATH, (proxy, error) => {
            if (error) { global.logError(`cinminai applet: ${error}`); this.refresh(); return; }
            this.proxy = proxy;
            proxy.connect("g-properties-changed", () => this.refresh());
            proxy.connect("notify::g-name-owner", () => this.refresh());
            this.refresh();
        }, null, Gio.DBusProxyFlags.DO_NOT_AUTO_START);
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
        this.set_applet_tooltip(`Assistant: ${words}\nClick to open or close (Super+A)`);
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
