# SPDX-License-Identifier: GPL-3.0-or-later
"""Transition knowledge base v0 (PLAN D23, D32): Windows habit -> Linux Mint, as short help cards.

This is what `lookup_help` returns at runtime and what the transition corpus is built from. Every
fact was checked on Linux Mint 22.3 (Cinnamon): program and settings names come from labels.json
(extracted from Mint's own .desktop files, so they match what the user sees in their language), and
labels such as "Layouts", "Network time", "Text scaling factor", "Panel settings", "Add to desktop",
"Extract Here", "Empty Trash", "Force Quit", "Screen reader", "Speed", "Acceleration", "Left handed", "Output", "Device",
"Install Updates", "New note", the Print / Shift+Print screenshot keys,
Ctrl+Alt+Delete (log out) and Ctrl+Alt+L (lock) were checked in Cinnamon's settings modules,
keybindings, and Nemo. Update this file with every OS release (D31).

Fields: id; windows = what the user knows from Windows (drives question generation); card = the help
text, `{key}` = a Mint name from labels.json in the user's language; must = label keys the reply has to
use (an inner list = any one of these names); steps = the reply should be numbered steps; langs = languages where every name is translated
(default: all six).
"""

ALL = ["en", "es", "pt", "fr", "de", "ja"]
BRANDS = {"writer", "calc", "impress", "timeshift", "video_player", "firefox", "pix", "onboard",
          "warpinator", "music_player", "drawing"}

TOPICS = [
    # --- installing and removing programs ---------------------------------------------------------
    {"id": "install", "windows": "downloading an .exe or .msi installer from a website to install a program",
     "card": "Installing programs: open the Menu (bottom-left, or press the Windows key), open "
             "{software_manager}, type the program's name in the search box, click it, then click Install and "
             "type your password. Windows .exe files don't run here; most popular programs have a version in "
             "{software_manager}.",
     "must": ["software_manager"], "steps": True},
    {"id": "uninstall", "windows": "Add or Remove Programs / Apps & features to uninstall a program",
     "card": "Uninstalling: open the Menu, right-click the program and choose Uninstall, then confirm and type "
             "your password. Or open {software_manager}, find the program, and click Remove.",
     "must": [], "steps": True},
    {"id": "store", "windows": "the Microsoft Store",
     "card": "App store: {software_manager} is the app store of Linux Mint. It's free, the programs are "
             "checked, and they get their updates through {update_manager}.",
     "must": ["software_manager"], "steps": False},
    {"id": "office", "windows": "Microsoft Office: Word, Excel and PowerPoint",
     "card": "Office: LibreOffice is already installed: {writer} for letters (like Word), {calc} for tables "
             "(like Excel) and {impress} for slides (like PowerPoint). They open and save Word, Excel and "
             "PowerPoint files. Microsoft 365 also works in {firefox}.",
     "must": ["writer", "calc"], "steps": False},
    {"id": "games", "windows": "installing and playing PC games",
     "card": "Games: install Steam from {software_manager}. Many Windows games run through Steam on Linux; "
             "Steam shows which ones work. Simple games are also in {software_manager}.",
     "must": ["software_manager"], "steps": False},

    # --- where things are -------------------------------------------------------------------------
    {"id": "control_panel", "windows": "Control Panel / Windows Settings",
     "card": "Control Panel: on Linux Mint it is called {system_settings}. Open the Menu (bottom-left) and "
             "click {system_settings} (the gear icon in the left column), or search for it by name.",
     "must": ["system_settings"], "steps": False},
    {"id": "start_menu", "windows": "the Start menu and the Start button",
     "card": "Start menu: it's the Menu button at the bottom-left of the screen (the Mint logo). The Windows "
             "key opens it too. Type to search for any program.",
     "must": [], "steps": False},
    {"id": "explorer", "windows": "File Explorer, This PC / My Computer, the C: drive",
     "card": "Drives and files: Linux has no drive letters. Open {files} (the folder icon in the panel). Your "
             "own files are in your Home folder, with Documents, Downloads, Pictures and so on, like on "
             "Windows. USB sticks and other disks show up in the left column of {files}.",
     "must": ["files"], "steps": False},
    {"id": "task_manager", "windows": "Task Manager and Ctrl+Alt+Del to end a frozen program",
     "card": "Task Manager: on Linux Mint it's {system_monitor}; its Processes tab lists running programs, "
             "select one and click End Process. Ctrl+Alt+Delete opens the log-out dialog instead. For a "
             "frozen window, click its X once and wait: Mint offers to Force Quit it.",
     "must": ["system_monitor"], "steps": False, "langs": ["en"]},
    {"id": "frozen", "windows": "a program that is Not Responding",
     "card": "Frozen program: click its X once and wait a few seconds; Mint then offers to Force Quit it. "
             "That closes it; unsaved work in that program is lost.",
     "must": [], "steps": False},
    {"id": "notepad", "windows": "Notepad",
     "card": "Notepad: on Linux Mint it's {text_editor}. Open the Menu and type 'text' to find it.",
     "must": ["text_editor"], "steps": False},
    {"id": "paint", "windows": "Paint / MS Paint",
     "card": "Paint: Linux Mint has {drawing} for simple pictures and edits. Open the Menu and type its name.",
     "must": ["drawing"], "steps": False},
    {"id": "photos", "windows": "the Photos app to look at and organise pictures",
     "card": "Photos: double-click a picture to open it in {image_viewer}. To organise your pictures, "
             "import from a camera or phone, and make albums, use {pix}.",
     "must": ["image_viewer"], "steps": False},
    {"id": "media", "windows": "Windows Media Player / Movies & TV",
     "card": "Videos and music: videos open in {video_player}; for your music collection use "
             "{music_player}. Both are already installed; double-click a file to play it.",
     "must": ["video_player"], "steps": False, "langs": ["en"]},
    {"id": "calculator", "windows": "the Calculator app",
     "card": "Calculator: open the Menu and type 'calc'; {calculator} is already installed. (LibreOffice "
             "{calc} is the spreadsheet, like Excel.)",
     "must": ["calculator"], "steps": False},
    {"id": "sticky", "windows": "Sticky Notes",
     "card": "Sticky notes: open {notes} from the Menu and make a New note; notes stay on your desktop and "
             "are saved automatically.",
     "must": ["notes"], "steps": False},
    {"id": "outlook", "windows": "Outlook / the Mail app for email",
     "card": "Email: {email} is already installed and works like Outlook. Open it from the Menu, type your "
             "name, email address and password, and it finds your provider's settings by itself.",
     "must": ["email"], "steps": True},
    {"id": "pdf", "windows": "opening PDF files (Adobe Reader / Edge)",
     "card": "PDF files: double-click the PDF and it opens in {document_viewer}. To fill in a form, type in "
             "its boxes and use File > Save a Copy.",
     "must": ["document_viewer"], "steps": False},
    {"id": "zip", "windows": "opening or extracting .zip files",
     "card": "Zip files: double-click a .zip to look inside with {archive_manager}. To unpack it, right-click "
             "the file in {files} and choose Extract Here.",
     "must": ["archive_manager"], "steps": False},
    {"id": "browser", "windows": "Microsoft Edge / Internet Explorer",
     "card": "Web browser: {firefox} is already installed; it's in the panel and the Menu. Chrome and other "
             "browsers can be installed from {software_manager}.",
     "must": ["firefox"], "steps": False},
    {"id": "recycle_bin", "windows": "the Recycle Bin",
     "card": "Recycle Bin: on Linux Mint it's the Trash, in the left column of {files}. Deleted files wait "
             "there; right-click a file to restore it, or right-click Trash and choose Empty Trash.",
     "must": ["files"], "steps": False, "langs": ["en"]},
    {"id": "char_map", "windows": "Character Map, typing special characters and symbols",
     "card": "Special characters: open {character_map} from the Menu, find the symbol, double-click it, "
             "then click Copy and paste it where you need it.",
     "must": ["character_map"], "steps": True},
    {"id": "scanner", "windows": "Windows Fax and Scan / scanning a letter",
     "card": "Scanning: open {document_scanner} from the Menu, put the page in the scanner, click Scan, "
             "then Save (PDF is best for letters).",
     "must": ["document_scanner"], "steps": True},
    {"id": "nearby_share", "windows": "Nearby Sharing / sending files to another computer on the same Wi-Fi",
     "card": "Sharing files nearby: open {warpinator} on both computers (on the same network), click the "
             "other computer's name, and drop the files in. Nothing goes through the internet.",
     "must": ["warpinator"], "steps": True},
    {"id": "onscreen_kb", "windows": "the on-screen keyboard",
     "card": "On-screen keyboard: open {onboard} from the Menu; it shows a keyboard you can type on with the "
             "mouse or a touchscreen.",
     "must": ["onboard"], "steps": False},

    # --- updates, safety, backups -----------------------------------------------------------------
    {"id": "windows_update", "windows": "Windows Update",
     "card": "Updates: {update_manager} does what Windows Update does. When updates are ready, its shield "
             "icon in the panel (bottom-right) shows a dot. Click it, then click {ui_install_updates} and type your "
             "password. It never restarts the computer by itself; it tells you if a restart is needed.",
     "must": ["update_manager"], "steps": True},
    {"id": "antivirus", "windows": "Windows Defender / needing an antivirus",
     "card": "Antivirus: Linux Mint doesn't need an antivirus for everyday use. What keeps it safe: install "
             "updates from {update_manager}, get programs from {software_manager} instead of random websites, "
             "and don't type your password when you don't know why it's asked. If you want to check files or "
             "USB sticks from other computers, ClamAV can be installed from {software_manager}; it's your "
             "choice.",
     "must": [["update_manager", "software_manager"]], "steps": False},
    {"id": "firewall", "windows": "Windows Defender Firewall",
     "card": "Firewall: open {firewall} from the Menu to see whether the firewall is on and to switch it on. "
             "For a home computer, on with the default settings is enough.",
     "must": ["firewall"], "steps": False},
    {"id": "system_restore", "windows": "System Restore / restore points",
     "card": "System Restore: {timeshift} takes snapshots of the system (not your personal files) so you can "
             "go back if an update causes trouble. Open it from the Menu, follow the setup wizard, and let it "
             "take daily snapshots. For your own files use {backup_tool}.",
     "must": ["timeshift"], "steps": False},
    {"id": "backup", "windows": "File History / backing up documents",
     "card": "Backups: your documents are only on this computer unless you back them up. {backup_tool} copies "
             "your Home folder to a USB stick or disk; plug one in, open it from the Menu, and follow the "
             "steps.",
     "must": ["backup_tool"], "steps": False},
    {"id": "microsoft_account", "windows": "signing in with a Microsoft account / OneDrive",
     "card": "Accounts: Linux Mint needs no online account; you log in with your own user name and password, "
             "and your files stay on this computer. OneDrive and other cloud storage still work in {firefox} "
             "if you want them.",
     "must": [], "steps": False},
    {"id": "admin_password", "windows": "User Account Control prompts and the administrator password",
     "card": "Passwords: the password Linux Mint asks for is your own login password, the one chosen during "
             "installation. Type it only when you started something yourself, like an update or an install. "
             "The assistant never knows or stores it. To change it, open {account}.",
     "must": ["account"], "steps": False},
    {"id": "lock_screen", "windows": "Windows+L to lock the computer",
     "card": "Locking the screen: press Ctrl+Alt+L (on Linux Mint, Windows+L does something else). Your "
             "programs stay open; type your password to come back.",
     "must": [], "steps": False},
    {"id": "drivers", "windows": "Device Manager and installing drivers",
     "card": "Drivers: most hardware works without installing anything. {driver_manager} lists extra drivers, "
             "for example for NVIDIA graphics cards; select the recommended one, click Apply Changes, type "
             "your password, and restart when it says so. {system_info} shows your hardware.",
     "must": ["driver_manager"], "steps": True},

    # --- settings ---------------------------------------------------------------------------------
    {"id": "wallpaper", "windows": "Personalize > Background to change the desktop wallpaper",
     "card": "Wallpaper: right-click an empty spot on the desktop and choose {change_background}. That opens "
             "{backgrounds}. Click a picture to use it; use the + button to add your own pictures folder.",
     "must": [["backgrounds", "change_background"]], "steps": True},
    {"id": "dark_mode", "windows": "dark mode in Windows Settings",
     "card": "Dark mode: open {themes} in {system_settings} and choose the Dark style (or a dark colour).",
     "must": ["themes"], "steps": False},
    {"id": "display_scale", "windows": "Display settings: resolution and scale (make everything bigger)",
     "card": "Screen size: open {display} in {system_settings}. Pick your screen, change Resolution or, better "
             "for tiny text, raise User interface scale, then click Apply and keep the new setting.",
     "must": ["display"], "steps": True},
    {"id": "text_size", "windows": "making text bigger everywhere (Ease of Access text size)",
     "card": "Bigger text everywhere: open {fonts} in {system_settings} and raise Text scaling factor (for "
             "example to 1.2). Or switch on Large text in {accessibility}. In Firefox, Ctrl and + zooms.",
     "must": ["fonts"], "steps": False},
    {"id": "screen_timeout", "windows": "Power & sleep: when the screen turns off",
     "card": "Screen turning off: open {power} in {system_settings} and change 'Turn off the screen when "
             "inactive for' to a longer time or Never. The lock after a delay is in {screensaver}.",
     "must": ["power"], "steps": False},
    {"id": "night_light", "windows": "Night light",
     "card": "Night light: open {night_light} in {system_settings} and switch it on. It makes the screen "
             "warmer in the evening, automatically.",
     "must": ["night_light"], "steps": False},
    {"id": "mouse", "windows": "Mouse settings: pointer speed, left-handed buttons",
     "card": "Mouse: open {mouse} in {system_settings}. Under Pointer size and speed, move the Speed or "
             "Acceleration slider; to swap the buttons, switch on Left handed.",
     "must": ["mouse"], "steps": False},
    {"id": "keyboard_layout", "windows": "adding a keyboard language/layout",
     "card": "Keyboard layout: open {keyboard} in {system_settings} and go to the Layouts tab. Click +, choose "
             "the language and layout, and click Add. Switch layouts with the flag or letters in the panel.",
     "must": ["keyboard"], "steps": True},
    {"id": "system_language", "windows": "changing the display language of Windows",
     "card": "System language: open {languages} from the Menu. Click Install / Remove Languages, add the "
             "language, then choose it as the Language and click Apply System-Wide. Log out and back in.",
     "must": ["languages"], "steps": True},
    {"id": "typing_japanese", "windows": "the Japanese IME (typing Japanese)",
     "card": "Typing Japanese: open {input_method} from the Menu. Under Japanese, click the button to install "
             "the language support, then choose IBus as the input method. Log out and back in. Press "
             "Super+Space (Windows key + Space) to switch between your keyboard and Japanese (Mozc).",
     "must": ["input_method"], "steps": True},
    {"id": "clock", "windows": "Date & time settings, time zone",
     "card": "Clock: open {date_time} in {system_settings}. Switch on Network time so the computer sets the "
             "clock by itself, and pick your Region and City so the time zone is right.",
     "must": ["date_time"], "steps": False},
    {"id": "startup_apps", "windows": "the Startup tab in Task Manager",
     "card": "Startup programs: open {startup_apps} from the Menu. Switch off the ones you don't want to start "
             "at login.",
     "must": ["startup_apps"], "steps": False},
    {"id": "default_apps", "windows": "Default apps (choosing the default browser)",
     "card": "Default programs: open {preferred_apps} in {system_settings} and choose the browser under Web, "
             "the mail program under Mail, and so on.",
     "must": ["preferred_apps"], "steps": False},
    {"id": "wifi", "windows": "connecting to Wi-Fi from the taskbar",
     "card": "Wi-Fi: click the network icon in the panel (bottom-right, next to the clock). Click your "
             "network's name, type the Wi-Fi password, and click Connect. It connects by itself next time. "
             "More options are in {network} in {system_settings}.",
     "must": ["network"], "steps": True},
    {"id": "bluetooth", "windows": "pairing Bluetooth headphones or a mouse",
     "card": "Bluetooth: put the device in pairing mode (see its manual), open {bluetooth} from the Menu or the "
             "Bluetooth icon in the panel, click Search, select the device and click Pair.",
     "must": ["bluetooth"], "steps": True},
    {"id": "sound_output", "windows": "choosing speakers or headphones for sound",
     "card": "Sound: click the speaker icon in the panel to change the volume. To choose speakers, headphones "
             "or the monitor, open {sound} in {system_settings}, go to Output, and pick the Device.",
     "must": ["sound"], "steps": False},
    {"id": "screen_reader", "windows": "Narrator (reading the screen aloud)",
     "card": "Reading aloud: open {accessibility} in {system_settings} and switch on Screen reader. It reads "
             "what's under the keyboard focus; the same page has Large text.",
     "must": ["accessibility"], "steps": False},
    {"id": "web_app", "windows": "pinning a website like an app",
     "card": "Web apps: open {web_apps} from the Menu, click +, type the site's name and address, pick an "
             "icon, and click OK. It then appears in the Menu like any program.",
     "must": ["web_apps"], "steps": True},

    # --- habits and shortcuts ------------------------------------------------------------------------
    {"id": "screenshot", "windows": "the Snipping Tool / Print Screen",
     "card": "Screenshots: press the Print Screen key (PrtSc) to capture the whole screen, or Shift+PrtSc to "
             "drag a box around just a part of it. {screenshot} in the Menu has more options (a delay, one "
             "window). Pictures are saved in your Pictures folder.",
     "must": [], "steps": False},
    {"id": "desktop_shortcut", "windows": "creating a desktop shortcut for a program",
     "card": "Desktop icon: open the Menu, find the program, right-click it and choose Add to desktop.",
     "must": [], "steps": True},
    {"id": "switch_windows", "windows": "Alt+Tab and the taskbar to switch windows",
     "card": "Switching windows: hold Alt and press Tab to go through open windows; let go to pick one. You "
             "can also click the program in the panel at the bottom of the screen.",
     "must": [], "steps": False},
    {"id": "taskbar", "windows": "taskbar settings (size, position)",
     "card": "The taskbar is called the panel. Right-click an empty part of it and choose Panel settings; "
             "there you can change its height and where it sits.",
     "must": [], "steps": False},
    # --- staying safe and private (SPEC §10.6, D28): used by the session corpus ---------------------
    {"id": "scam_email", "windows": "an email from 'the bank' asking to confirm a PIN or password at a link",
     "card": "Scams: banks never ask for your PIN, password or card number by email, text message or phone call. "
             "Don't click the link or reply. If you're worried, call the number on the back of your card. "
             "Cin-MinAI never calls, emails, or asks for money or passwords either.",
     "must": [], "steps": False},
    {"id": "scam_phone", "windows": "a phone call from 'Microsoft support' saying the computer has a virus",
     "card": "Phone scams: Microsoft, banks, and Cin-MinAI never call you about viruses. Hang up. Never let a "
             "caller connect to your computer, and never pay them or give them a password or card number.",
     "must": [], "steps": False},
    {"id": "scam_popup", "windows": "a web page saying the computer is infected and to call a number",
     "card": "Fake virus warnings: a web page that says your computer is infected and gives a phone number is a "
             "scam. Don't call. Close the page (Ctrl+W, or close {firefox}). Nothing on this computer tells you "
             "to call a number.",
     "must": [], "steps": False},
    {"id": "privacy_assistant", "windows": "whether the AI assistant sends what they type to the internet",
     # update 5 (2026-10-07): says what is really sent, and when (D86: the promise matches the features). The old card
     # promised a WEB sign in the panel that was never built.
     "card": "Privacy: the assistant runs on this computer. What you type stays here. Something is sent only when "
             "you ask for it: a web search sends its words to DuckDuckGo (or to Bing, if DuckDuckGo asks for a "
             "pause); the news sends its topic to Google News, Bing, Reddit and Mastodon; and a news watch you set "
             "up sends its topic once a day until you pause or delete it under Standing tasks. Each time, a card "
             "first shows the exact words and where they go. Nothing about you or this computer is sent.",
     "must": [], "steps": False},
    {"id": "offline_mode", "windows": "keeping the computer completely off the internet",
     # update 5 (2026-10-07): offline mode is planned (PLAN D28, M5) and not built yet; the old card described its
     # switch as if it were there
     "card": "Offline mode: a switch that keeps this computer off the internet, with one button to go online for "
             "updates, is planned but not in this version yet. Until then: click the network icon in the panel and "
             "switch off Wi-Fi, or unplug the network cable. The assistant itself works without the internet; "
             "only web searches and the news need it.",
     "must": [], "steps": True},

    # --- update 5 (2026-10-07): the news scan (D92), standing tasks (D88) and keys for sources ------------------------
    {"id": "news_scan", "windows": "news apps or a news feed (MSN News, Google News)",
     "card": "News: ask the assistant for the news about something, for example \"pull up the news about Linux "
             "Mint\" or \"what's the latest on the Artemis mission?\". It shows what's on hand, in three parts: news "
             "outlets' headlines word for word with the outlet and date; posts from Reddit and Mastodon with who "
             "posted them (claims nobody checked); and the subject's own or official pages. It never says what "
             "happened, only who says what, so you can decide for yourself. Before anything is sent, a card shows "
             "the topic and where it goes; click Search. Add \"on Reddit\" to ask Reddit only. X and Bluesky aren't "
             "included: searching them needs an account.",
     "must": [], "steps": False},
    {"id": "standing_tasks", "windows": "getting news alerts or scheduled updates about a topic",
     "card": "Standing tasks: things the assistant keeps doing for you, like watching the news about a topic. "
             "Ask \"keep me up to date on …\" or \"the news about … every morning\"; a card shows the topic, the "
             "time and where the topic is sent every day; click Set up. After that it looks once a day and shows "
             "only what's new, with a notification. To see them, pause them or delete them: click Standing tasks "
             "on the assistant's start screen, or right-click the assistant's icon in the panel and choose "
             "Standing tasks.",
     "must": [], "steps": True},
    {"id": "source_keys", "windows": "an API key, or a website asking you to register for a key",
     "card": "Keys for sources: some sources of information only answer people with a free key, like a library "
             "card. When one is needed, the assistant shows a card with the steps to get it, a button to their "
             "sign-up page and a box to paste the key in; you register on their site yourself. The key is kept in "
             "your login keyring, locked by your login password; it never goes into the conversation, and the "
             "assistant itself never reads it. If you paste a key into the chat by mistake, it isn't kept.",
     "must": [], "steps": False},
    {"id": "updates_why", "windows": "whether updates matter, and whether they are like antivirus definitions",
     "card": "Updates: security updates fix weaknesses in the programs themselves, the holes criminals look for. "
             "That's different from an antivirus's list of known threats. {update_manager} checks that every "
             "update is genuine (signed) before installing it, and you can watch each check happen.",
     "must": ["update_manager"], "steps": False},
    {"id": "word_files", "windows": "opening .docx files from Word",
     "card": "Word files: double-click a .docx file and it opens in {writer}, which is already installed. To "
             "send one back as Word, use File > Save As and pick Word (.docx); click 'Use Word 2007-365!' if "
             "asked.",
     "must": ["writer"], "steps": False},

    # --- D84 batch 1 (2026-10-06): the everyday pictures are Ian's; steps checked on the test SSD's own files ---------
    {"id": "vpn", "windows": "a VPN app or Windows' VPN settings",
     "card": "VPN: think of a PO box. A VPN service is like a post office full of PO boxes: many people's "
             "connections leave from the same address, so websites see the service, not you. But the service knows "
             "which box is yours and can be required to hand that over to the authorities. A private VPN, one you "
             "set up yourself, is like a mailbox you put in the middle of nowhere: people can reach the box, but no "
             "one has a line from it to you. Either way, what you send stays confidential on the way. Worth it on "
             "public Wi-Fi, to reach a home or work network, or to appear in another country; it doesn't make you "
             "anonymous, and it can slow the connection a little. To add one: open {system_settings}, then "
             "{network}, click + at the bottom left, choose {ui_import_from_file} and pick the .ovpn file your VPN "
             "service gave you (or choose OpenVPN and type in its details), then switch it on in the list. If the "
             "service has its own Linux app, that works too.",
     "must": ["network"], "steps": True},
    {"id": "keyring", "windows": "Windows Credential Manager, or a window asking for a 'keyring' password",
     "card": "Keyring: the keyring is a locked box for your saved passwords and keys (Wi-Fi, email, websites). "
             "Its password is not like a normal password: it unlocks the keys themselves, so whoever unlocks it gets "
             "past the first layer of protection (other systems call it a key vault). It normally opens by itself "
             "when you log in, because it uses your login password. It asks on its own when you log in "
             "automatically (no password was typed), or after your login password changed and the keyring's "
             "didn't: then type the password it was made with. To make them match again, open {passwords_keys}, "
             "right-click Login, choose {ui_change_password}, and enter the old password, then the new one. Don't delete "
             "the Login keyring to stop the question: the passwords saved in it would be lost.",
     "must": ["passwords_keys"], "steps": True, "langs": ["en", "es", "pt", "fr", "de"]},
    {"id": "hidden_files", "windows": "'Show hidden files' in File Explorer",
     "card": "Hidden files: some files are hidden for your convenience. Their names start with a dot (like "
             ".config), and they hold what your programs need to work the way you expect. Deleting one usually "
             "won't break the computer itself (though it can), but it can break a program or wipe its settings. To "
             "see them in {files}: press Ctrl+H (careful: don't delete or change them unless you know what a file "
             "is for, or a guide you trust says to), or choose {ui_view} > {ui_show_hidden_files}; press Ctrl+H again to "
             "hide them.",
     "must": ["files"], "steps": True},
    {"id": "user_accounts", "windows": "adding a family member or another user account",
     "card": "User accounts: accounts are free, and every person can have their own experience: their own files, "
             "settings, browser and saved passwords, behind a password of their own. Make one for each person "
             "instead of sharing. Standard is right for most people, children included; an Administrator can "
             "install programs and change the system. To add one: open {users} and type your password, click {ui_add}, "
             "choose the {ui_account_type} ({ui_standard} or {ui_administrator}), fill in {ui_full_name} and "
             "{ui_username}, and click {ui_add}. Then click the new account, click {ui_no_password_set} next to "
             "{ui_password}, and give it a password.",
     "must": ["users"], "steps": True},
    {"id": "bootable_usb", "windows": "Rufus or the Media Creation Tool, to make a bootable USB stick from an ISO",
     "card": "Bootable USB stick: two words first. A disk image is a map of how to set every bit on a disk; a "
             "disk volume is how those bits are read back as files and folders. An .iso file is a system image: "
             "written onto a USB stick, it makes the stick a disk that can start a computer and build the system's "
             "volume on its drive. That's why you write it instead of copying it: a copy would just be one file on "
             "the stick. To make one: writing erases everything on the stick, so first save any files you want "
             "from it to your computer; plug in the stick, open {usb_writer}, click {ui_select_image} and choose the "
             ".iso file, "
             "choose the stick under {ui_usb_stick} click {ui_write} (this erases the stick) and type your password. To use "
             "the stick for files again later, open {usb_formatter}, choose "
             "the stick, give it a name and click {ui_format}. A Windows .iso usually needs Windows' own tool; the "
             "writer warns you when it sees one.",
     "must": ["usb_writer"], "steps": True},
    {"id": "aicui", "windows": "Visual Studio Code or another IDE for programming",
     "card": "AICUI: a coding workspace made for working with an AI. The AI can run the developer tools itself, "
             "so it needs little more than a terminal; AICUI is there so you can see your project while it works: "
             "the files and what changed, the goals for the session, the AI's own terminal, and a changelog where "
             "every change can be undone. It asks before it changes anything unless you choose otherwise. To start: "
             "open the Menu, then Programming, then AICUI (or click Open AICUI in the assistant's sidebar), choose "
             "your project folder, type what you want in the box at the bottom and click Send to the AI.",
     "must": [], "steps": True, "langs": ["en"]},

    # --- D84 batch 2 (2026-10-06): pictures for usb_format, software_sources and specs ("what's under the hood", the
    # window sticker) are Ian's; the others were drafted by Claude and reviewed by Ian. Steps checked against the
    # release ISO's and the test SSD's own program files ----------------------------------------------------------------
    {"id": "usb_format", "windows": "formatting a USB stick (right-click > Format in File Explorer)",
     "card": "Formatting a USB stick: a stick keeps your files in buckets, and a map (the file system) indexes "
             "which bucket holds what, so the computer can grab the one you want when you need it. Formatting "
             "throws everything away and builds new, empty buckets and a fresh map. Do it to use a stick for "
             "files again after it held a system image, or when it acts up. FAT32 works with nearly everything "
             "(TVs, car stereos, Windows, Mac); exFAT also takes files bigger than 4 GB; NTFS is Windows' own; "
             "EXT4 is for Linux only. To format: first save any files you want from the stick to your computer, "
             "because formatting erases them; open {usb_formatter}, choose the stick, type a name for it, pick the "
             "{ui_filesystem} type, click {ui_format} (this erases the stick) and type your password.",
     "must": ["usb_formatter"], "steps": True},
    {"id": "software_sources", "windows": "where to download programs safely, or adding a software source",
     "card": "Software sources: a software source is anyone who provides software: a website, a torrent, a "
             "manufacturer, a person. Known and trusted sources are always best. Linux Mint's own sources, the ones "
             "{software_manager} and {update_manager} use, are checked and signed. Adding another source (a PPA or "
             "a repository) means trusting whoever runs it with your whole computer, so add one only when the "
             "program's own makers tell you to. When you can't find a trusted source, being your own source beats "
             "an unknown one: build the small tool yourself (AICUI can help). Sources are kept in "
             "{software_sources} (not in {software_manager}). To add a PPA the makers gave you: open "
             "{software_sources} and type your password, open {ui_ppas}, click {ui_sources_add} and paste its "
             "address. To pick a faster download server: in {software_sources}, on {ui_official_repositories}, "
             "click the server next to {ui_mirror_main}, choose the fastest one and click {ui_apply}.",
     "must": ["software_sources"], "steps": True},
    {"id": "panel", "windows": "the taskbar: moving it, pinning programs, adding things to it",
     "card": "Panel: the panel is the strip along the bottom of the screen, like the Windows taskbar: the Menu "
             "button, your open windows, and small tools (applets) such as the clock, sound and network. To pin a "
             "program: open the Menu, right-click the program and choose {ui_add_to_panel}. To move the panel to "
             "another edge: right-click an empty spot on it and choose {ui_panel_move}. For its size and hiding: "
             "right-click it and choose {ui_panel_settings}. To add a tool: right-click it, choose {ui_applets}, "
             "pick one on {ui_manage} and click {ui_add}; more are under {ui_download}.",
     "must": [], "steps": True},
    {"id": "online_accounts", "windows": "signing in with a Microsoft or Google account in Windows settings",
     "card": "Online accounts: think of a key you hand over once at the front desk: you sign in to your Google or "
             "Microsoft account one time, and the programs that know about it, like {calendar}, use it without "
             "asking again. It gives those programs access to that account; you can remove it there any time. To "
             "add one: open {online_accounts}, choose your provider (for example Google or Microsoft) and sign in "
             "in the window that opens. Your password goes to Google or Microsoft, not to the assistant. Then open "
             "{calendar} to see your events.",
     "must": ["online_accounts"], "steps": True},
    {"id": "notifications", "windows": "Focus Assist or turning off notifications in Windows",
     "card": "Notifications: the small messages in the corner of the screen are like a doorbell; you can turn the "
             "bell down or off. Open {system_settings}, then {notifications}: switch off {ui_enable_notifications} "
             "to silence them all, or make them go away sooner with {ui_notification_duration}.",
     "must": ["notifications"], "steps": True},
    {"id": "auto_login", "windows": "signing in automatically without a password",
     "card": "Automatic login: it's like leaving the front door unlocked. Handy when you live alone and the "
             "computer stays home, but anyone who turns it on is in, and the keyring will ask for its password "
             "after each start (nothing typed at login unlocks it). Not for a laptop that leaves the house. To "
             "switch it on or off: open {login_window} and type your password, open the {ui_users_tab} tab, and "
             "under {ui_automatic_login} choose your name in {ui_lightdm_username}, or clear it to switch automatic "
             "login off.",
     "must": ["login_window"], "steps": True},
    {"id": "disk_health", "windows": "a hard drive's health status, CHKDSK or the drive's SMART status",
     "card": "Disk health: drives report their own health, like warning lights on a car's dashboard. To read them: "
             "open {disks}, click the drive in the left column, click the ⋮ button at the top right and choose "
             "{ui_smart}. {ui_overall_assessment} says whether the drive is OK. If it reports problems, back up "
             "your files now. Careful: {disks} can also erase drives; for USB sticks use {usb_formatter} instead.",
     "must": ["disks"], "steps": True},
    {"id": "specs", "windows": "System Information or 'About your PC': what processor, memory and graphics card I have",
     "card": "What's under the hood: {system_info} is like the window sticker on a new car. A spec list only "
             "names the hardware; this shows the parts and the system together: the operating system, the Linux "
             "kernel and the desktop, then the processor, memory and graphics card. Open {system_info}; "
             "{ui_system_information} shows it all. Click {ui_copy} to paste it into a forum post or a message "
             "when someone asks what you're running. You can also just ask the assistant, which can check this "
             "computer for you.",
     "must": ["system_info"], "steps": True},
    {"id": "battery", "windows": "battery settings and battery saver on a laptop",
     "card": "Battery: the battery icon in the panel is your fuel gauge: point at it or click it to see how full it "
             "is and how long it will last. To choose what happens when you close the lid, how soon the screen "
             "dims and when the computer sleeps on battery: open {system_settings}, then {power}, and set "
             "{ui_lid_closed} and the other times there.",
     "must": ["power"], "steps": True},
    {"id": "live_usb", "windows": "trying Linux from a USB stick before installing it",
     "card": "Trying it from the USB stick: started from the stick, the system is like a test drive. Nothing on "
             "the computer changes, and anything you make or download is gone when you shut down, so keep files on "
             "another USB stick. It's slower than after installing. When you're ready to keep it: back up your "
             "files first, then double-click {install_cinminai} on the desktop and follow the steps.",
     "must": ["install_cinminai"], "steps": True},

    # --- from the hands-on round on the test SSD (2026-10-07): questions the guide answered with invented steps. The
    # system checks behind them are inspect_system "account", "memory", "temperature"; pictures drafted by Claude for
    # Ian to review ---------------------------------------------------------------------------------------------------
    {"id": "admin_account", "windows": "whether my account is an administrator account",
     "card": "Administrator or standard account: an administrator account is like holding the building's master key: "
             "it can install programs and change the system, after typing its own password each time. The account "
             "made when the computer was installed is an administrator; others can be Standard. The assistant can "
             "check yours for you. To see any account's type: open {users} and type your password, then click the "
             "account: {ui_account_type} shows {ui_standard} or {ui_administrator}.",
     "must": ["users"], "steps": False},
    {"id": "memory_use", "windows": "Task Manager's Performance tab: how busy the computer is right now",
     "card": "Memory in use: it's the computer's desk space for what's open right now, not the cupboard where "
             "files are stored. What's installed and what's in use are two different numbers; the assistant can "
             "check both. To watch it yourself: open {system_monitor} and click {ui_resources}. If "
             "it's nearly full all the time, close programs and browser tabs you aren't using.",
     "must": ["system_monitor"], "steps": True},
    {"id": "temperatures", "windows": "checking CPU and GPU temperatures",
     "card": "Temperatures: the processor and graphics card measure their own heat, like a thermometer built into "
             "an engine. Up to about 80 °C is normal when they're busy; above 90 °C, check that the fans turn and "
             "the vents aren't full of dust. The assistant can read the sensors for you. Linux Mint has no "
             "temperature program built in: to watch them yourself, install Psensor from {software_manager}.",
     "must": ["software_manager"], "steps": False},
]
