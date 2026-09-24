// Cin-MinAI panel applet (M0 desktop-surface spike, SPEC §5.2).
// Shows the assistant's state from org.cinminai.Assistant1, awareness switches, and opens the sidebar.

const Applet = imports.ui.applet;
const PopupMenu = imports.ui.popupMenu;
const Util = imports.misc.util;
const Gio = imports.gi.Gio;
const GLib = imports.gi.GLib;

const BUS_NAME = "org.cinminai.Assistant1";
const OBJ_PATH = "/org/cinminai/Assistant1";
const IFACE_XML = `
<node>
  <interface name="org.cinminai.Assistant1">
    <property name="State" type="s" access="read"/>
    <property name="Model" type="s" access="read"/>
    <property name="Awareness" type="a{sb}" access="readwrite"/>
  </interface>
</node>`;
const AssistantProxy = Gio.DBusProxy.makeProxyWrapper(IFACE_XML);

const ICONS = {
    idle: "user-available-symbolic",
    thinking: "emblem-synchronizing-symbolic",
    approval: "dialog-warning-symbolic",
    off: "user-offline-symbolic",
    error: "dialog-error-symbolic",
    offline: "network-offline-symbolic",
};
const LABELS = {
    idle: "Idle", thinking: "Thinking…", approval: "Needs approval", off: "Off",
    error: "Error", offline: "Daemon not running",
};
const AWARENESS = [["terminals", "See terminals"], ["browser", "See browser"], ["web", "Web search"]];

class CinMinAIApplet extends Applet.IconApplet {
    constructor(metadata, orientation, panelHeight, instanceId) {
        super(orientation, panelHeight, instanceId);
        // install.sh links this; a package would install /usr/bin/cinminai-sidebar.
        this.sidebar = GLib.build_filenamev([GLib.get_home_dir(), ".local", "bin", "cinminai-sidebar"]);

        this.menuManager = new PopupMenu.PopupMenuManager(this);
        this.menu = new Applet.AppletPopupMenu(this, orientation);
        this.menuManager.addMenu(this.menu);

        this.stateItem = new PopupMenu.PopupMenuItem("", { reactive: false });
        this.modelItem = new PopupMenu.PopupMenuItem("", { reactive: false });
        this.menu.addMenuItem(this.stateItem);
        this.menu.addMenuItem(this.modelItem);
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this.switches = {};
        for (const [key, label] of AWARENESS) {
            const item = new PopupMenu.PopupSwitchMenuItem(label, false);
            item.connect("toggled", (it, on) => this.setAwareness(key, on));
            this.switches[key] = item;
            this.menu.addMenuItem(item);
        }
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this.menu.addAction("Open assistant", () => this.runSidebar("--show"));

        this.proxy = null;
        // Don't auto-start the daemon just because the panel loaded; show "offline" instead.
        new AssistantProxy(Gio.DBus.session, BUS_NAME, OBJ_PATH, (proxy, error) => {
            if (error) { global.logError(`cinminai: ${error}`); this.refresh(); return; }
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
        this.set_applet_icon_symbolic_name(ICONS[state] || ICONS.error);
        this.set_applet_tooltip(`Cin-MinAI: ${LABELS[state] || state}`);
        this.stateItem.label.set_text(`Assistant: ${LABELS[state] || state}`);
        const online = state !== "offline";
        this.modelItem.label.set_text(online ? `Model: ${this.proxy.Model}` : "Model: —");
        const aware = online && this.proxy.Awareness ? this.proxy.Awareness : {};
        for (const [key] of AWARENESS) {
            this.switches[key].setToggleState(!!aware[key]);
            this.switches[key].setSensitive(online);
        }
    }

    setAwareness(key, on) {
        if (!this.proxy) return;
        const value = new GLib.Variant("a{sb}", { [key]: on });
        this.proxy.call("org.freedesktop.DBus.Properties.Set",
            new GLib.Variant("(ssv)", ["org.cinminai.Assistant1", "Awareness", value]),
            Gio.DBusCallFlags.NONE, -1, null, null);
    }

    runSidebar(arg) {
        Util.spawn([this.sidebar, arg]);
    }

    on_applet_clicked() {
        this.menu.toggle();
    }

    on_applet_middle_clicked() {
        this.runSidebar("--toggle");
    }
}

function main(metadata, orientation, panelHeight, instanceId) {
    return new CinMinAIApplet(metadata, orientation, panelHeight, instanceId);
}
