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
             "icon in the panel (bottom-right) shows a dot. Click it, then click Install Updates and type your "
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
     "card": "Privacy: the assistant runs on this computer. What you type stays here; nothing is sent anywhere "
             "unless you ask it to search the web, and the panel shows WEB when that happens. In offline mode "
             "the computer doesn't connect to the internet at all.",
     "must": [], "steps": False},
    {"id": "offline_mode", "windows": "keeping the computer completely off the internet",
     "card": "Offline mode: click the gear button at the top of the assistant's sidebar and switch on Keep this computer offline. Wi-Fi and "
             "cable are both switched off and the panel shows OFFLINE. For security updates, click Go online to "
             "install updates; it connects, installs them, and disconnects again.",
     "must": [], "steps": True},
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
]
