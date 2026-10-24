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
    # D84 (2026-10-23): the Updates window (D29, D89) replaced Update Manager as the way in; the delivery and the phone
    # update pictures are drafted by Claude for Ian's review
    {"id": "windows_update", "windows": "Windows Update",
     "card": "Updates: think of a delivery checked at the door. {updates_window} shows what's waiting in plain "
             "words, security fixes first, and checks everything before it goes in: that it comes from who it says "
             "(signed), a safety snapshot first if Timeshift is set up, and every file against the signed list. It "
             "never restarts the computer by itself; it says when a restart is needed. To install: open "
             "{updates_window} from the assistant's start screen, or right-click the assistant's icon in the panel "
             "and choose {updates_window}; untick any you want to leave for now; click the Install button at the "
             "bottom (it says how many) and type your password; then watch each check. Under the list: "
             "{ui_updates_wait} for a few days, like waiting after a new phone update so others find a problem "
             "first (a security fix Debian's security team confirms still goes at once); {ui_updates_daily}; and "
             "{ui_updates_hold} on an update's row, then {ui_updates_hold_update} or {ui_updates_hold_program}. "
             "Click {ui_updates_save} and type your password to keep the settings. {update_manager} is still "
             "there: {ui_updates_expert}, at the bottom.",
     "must": ["updates_window"], "steps": True},
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
     # update 5 (2026-10-07) said offline mode was planned; built 2026-10-21 (PLAN D28)
     "card": "Offline mode: right-click the assistant's icon in the panel and switch on Keep this computer offline. "
             "Wi-Fi and the cable are switched off for the whole computer, the panel says OFFLINE, and the "
             "assistant doesn't offer web searches or downloads. To install updates, choose Go online to install "
             "updates in the same menu: {updates_window} opens, goes online for the check and the install, and "
             "goes back offline by itself once any install has finished. Once a month at most, a reminder says when security "
             "updates are due. To stay online again, switch Keep this computer offline off. The assistant itself "
             "works without the internet.",
     "must": [], "steps": True},
    # D84 (2026-10-23): the Library view (D68); the bookshelf and pocket-edition pictures are drafted by Claude for
    # Ian's review
    {"id": "wikipedia_library", "windows": "an encyclopedia app, or downloading Wikipedia to read offline",
     "card": "Library: think of an encyclopedia set on your own shelf instead of a trip to the library. With "
             "Wikipedia on this computer, the assistant looks things up at home: nothing is sent, nobody sees what "
             "you asked, and it works without the internet. The files come from Kiwix: the best-known articles with "
             "pictures are the illustrated set, and the summaries are a pocket edition of every article. They take "
             "disk space, from about 0.1 GB (the best-known articles' summaries) to over 100 GB (all of English "
             "Wikipedia with pictures). Without one, the assistant offers to read the article online, after you "
             "agree. To get one: open the assistant and click {ui_library} on its start screen (or right-click the "
             "assistant's icon in the panel and choose {ui_library}); click {ui_library_look} (only your choice of "
             "language is sent to Kiwix); then click {ui_library_get} next to the one you want. It downloads in the "
             "background while you keep using the computer, and it's checked before the assistant uses it. To take "
             "one off, click {ui_library_remove} next to it, then click again to confirm.",
     "must": [], "steps": True},

    # --- D84 batch 1 of our own features (2026-10-24; pictures drafted by Claude, approved by Ian: "Those are great");
    # words checked against sidebar/app.py, daemon/journal.py, webvideo.py, video.py; names in English where the
    # sidebar shows them in English (extract_labels.OWN_UI_EN) ------------------------------------------------------
    {"id": "the_assistant", "windows": "Copilot, Cortana or the search box on the taskbar",
     "card": "The assistant: think of a knowledgeable friend sitting at the side of your desk. Press Super+A (the "
             "Windows key and A), or click the assistant's icon in the panel, to bring it in; do it again (or press "
             "Esc) to send it away. It docks on the right of the screen without covering your windows. It runs on "
             "this computer: what you type stays here, and nothing is sent unless you agree, for example to a web "
             "search, which shows exactly what would be sent first. Its start screen has buttons for writing, the "
             "journal, coding and its other windows. To start over, click New… at the top and choose "
             "{ui_new_conversation} (or right-click its icon in the panel and choose {ui_new_conversation}). Hiding "
             "it keeps the conversation; restarting the computer starts a new one.",
     "must": [], "steps": True},
    {"id": "writing_projects", "windows": "writing a story or a novel in Word",
     "card": "Writing projects: like telling your story to a friend who takes notes while you talk, then asks "
             "what's still missing before each chapter. Click {ui_write_start} on the assistant's start screen (or "
             "New… at the top, then {ui_write_new}), give it a working title and choose one chapter or several. Then "
             "tell it about the story: the people, the places, what happens, how it should feel. It keeps "
             "{ui_write_notes}, along Dan Harmon's story circle (eight steps, from You to Change). When you're "
             "ready, click {ui_write_up}: it shows where the story is and asks its questions; answer if you like, "
             "then click {ui_write_plan}. It lays out the scenes: say what should change, or click {ui_write_it}. "
             "Each chapter is written as a new file and opens in {writer}; it never writes over the last one. The "
             "files are in Documents, then Writing, then the project's title. When the story is done, "
             "{ui_write_manuscript} in {ui_write_notes} makes a copy in the standard format for sending to "
             "publishers, as .odt and .docx.",
     "must": [], "steps": True},
    {"id": "journal", "windows": "a diary app, or keeping a journal in Word or OneNote",
     "card": "Journal: like ending the day with a good listener who only asks questions (never advice, never "
             "judging) and then writes it up in your own words. Click {ui_journal_open} on the assistant's start "
             "screen (or New… at the top, then {ui_journal}) and tell it about your day; it asks one short question "
             "at a time. When you're done, click {ui_journal_write}: the entry is written in your words, saved in "
             "Documents, then Journal, and opened in {writer}. To keep an entry private, tick {ui_journal_private} "
             "before writing it. The first time, you choose a 4-digit PIN: think of a diary with a lock, and the PIN "
             "as its key. A private entry is locked against people looking, the assistant can't read it while it's "
             "locked, and it opens only inside the assistant, from {ui_journal_entries}, with the PIN. Don't lose "
             "the PIN: there's no way to reset it, and without it a private entry can't be opened. The assistant "
             "hears what you tell it while the entry is being written; the conversation itself isn't kept.",
     "must": [], "steps": True},
    {"id": "ai_models", "windows": "choosing which AI model an app uses, or downloading one",
     "card": "Models: like the staff list of a small shop, each job has someone on it. Click {ui_models} on the "
             "assistant's start screen, or right-click the assistant's icon in the panel and choose {ui_models}. "
             "Each job (writing, pictures and video, writing code) shows the model on it, {ui_models_ours} or your "
             "choice; {ui_models_system} always stays with the built-in guide, because it holds the system's tools. "
             "To put another model on a job, pick it from the list beside the job: each says whether it runs well "
             "here, slowly, or not at all. {ui_models_more} searches Hugging Face for others; only your search "
             "words are sent. {ui_models_check} is measuring the doorway before you buy the sofa: it checks the "
             "model fits this computer before anything is downloaded. A download is checked against its checksum "
             "before it's used, and a stopped one carries on later. A model kept on another drive comes back with "
             "{ui_models_drives}. To take off a downloaded model no job uses, click {ui_library_remove} next to it, "
             "then click again to confirm.",
     "must": [], "steps": True},
    {"id": "video_summaries", "windows": "a YouTube summary extension, or watching a video file in a player",
     "card": "Video summaries: like a friend who watched the video and tells you the main points, with the times so "
             "you can check for yourself. For YouTube: open the video in Firefox and ask the assistant \"summarize "
             "this video\". It reads the video's transcript and its preview pictures (youtube.com only), so the ads "
             "aren't in it; a long video is done in parts. To find one first, ask for example \"find a video about "
             "baking bread\": a card shows what would be searched, and nothing is sent until you click Search. For a "
             "video file on this computer: drop it on the assistant, or click the picture button beside the box and "
             "choose it. It takes a few minutes, like someone listening to the whole recording, and you can do "
             "other things meanwhile; speech in any of the languages is understood. The first time, a card offers "
             "what it needs to download once (the speech reader is about 465 MB), checked when it arrives; nothing "
             "leaves this computer when it watches.",
     "must": [], "steps": True},
    # --- D84 batch 2 (Ian, 2026-10-24: "pictures are good") -----------------------------------------------------------
    {"id": "requests", "windows": "the print queue, or Task Manager's list of what's running",
     "card": "Requests: like the order tickets on a restaurant's rail. Each thing you asked the assistant is a "
             "ticket: what it was, which model is on it, and whether it's waiting, working or done, with the smaller "
             "tasks under it (a look, a check, a piece of code). Click {ui_requests} on the assistant's start screen "
             "(or New… at the top, then {ui_requests}, or right-click the assistant's icon in the panel and choose "
             "{ui_requests}). {ui_requests_stop} next to one that isn't finished takes it off the rail: a waiting one "
             "never starts, a running one stops. {ui_requests_refresh} shows the latest.",
     "must": [], "steps": True},
    {"id": "terminal_sharing", "windows": "sending someone a screenshot of an error message",
     "card": "Terminal sharing: like letting a friend look over your shoulder when something goes wrong, instead of "
             "reading the error out to them over the phone. It's off until you turn it on: click New… at the top of "
             "the assistant and tick {ui_terminal_share} (it also offers once, when a terminal question comes up). "
             "Terminals opened after that show ◆ at the start of the prompt: the assistant can read their commands "
             "and what they printed, so you can ask \"why did that fail?\". Terminals already open stay private until "
             "you close and reopen them. Typing ai off in a terminal is turning the screen away: that one stays "
             "private. Password prompts are never seen, and nothing leaves this computer. Untick it to stop.",
     "must": [], "steps": True},
    {"id": "internet_log", "windows": "a firewall's connection log, or the list of calls on a phone bill",
     "card": "The internet log: like the list of calls on a phone bill: who was called and when, never what was said. "
             "It's off unless you switch it on: right-click the assistant's icon in the panel and tick "
             "{ui_log_switch}; then {ui_log_open} in the same menu shows it. Each line is one connection: when, WEB "
             "(a website or search) or CLOUD (a cloud model you gave a key for), and where to; never what was sent. "
             "Without the log, the panel shows the same thing live, like an \"on air\" light: WEB or CLOUD beside "
             "the assistant's icon while something is going out, nothing while everything stays on this computer.",
     "must": [], "steps": True},
    {"id": "libreoffice_helper", "windows": "Copilot in Word or Excel",
     "card": "The assistant in LibreOffice: like a helper at your desk who suggests changes in pencil: nothing is "
             "inked until you say so, and one Undo takes it all back. It only sees a document you share. In "
             "{writer}, {calc} or {impress}, open the {ui_lo_menu} menu and choose {ui_lo_share}, then ask in the "
             "assistant, for example \"add a total row\". A change comes as a card showing before and after: "
             "{ui_lo_apply} puts it in, {ui_lo_discard} leaves the document as it was. The same menu has "
             "{ui_lo_ask}, {ui_lo_rewrite}, {ui_lo_explain} and {ui_lo_summarize} (choosing one shares the document "
             "too); {ui_lo_unshare} ends it. Nothing leaves this computer.",
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
             "your project folder, type what you want in the box at the bottom and click Send to the AI. To end "
             "everything at once (the AI, its models, its commands and what Run started), click Stop everything in "
             "the middle of the top bar; what was done stays, with undo. To measure how much your setup holds on "
             "this graphics card, click Benchmark in the top bar (it asks first, and can take an hour or more); "
             "Context, beside it, sets how much each model keeps in mind.",
     "must": [], "steps": True, "langs": ["en"]},
    # --- update 7 (2026-10-21): AICUI's GitHub flow and the Team Table; words checked against aicui/app.py and
    # aicui/tableview.py ------------------------------------------------------------------------------------------
    {"id": "aicui_github", "windows": "putting a project online: GitHub Desktop, or publishing a website",
     "card": "Publishing from AICUI: GitHub is a website that keeps projects, and GitHub Pages shows a project as a "
             "web page anyone can open, so a page you built can be shared by its address. AICUI does the git work "
             "for you and shows the files before anything goes: untick what should stay private. A published page "
             "is public. To start: in AICUI, click GitHub at the top right, choose Sign in to GitHub… and type the "
             "code it shows on GitHub's page in your browser (AICUI never sees your password). Then choose Link this "
             "project to a repository… (AICUI can make a new one for you), and Save to GitHub (push) or Publish as a "
             "web page (GitHub Pages)…. To start from someone's project: choose Clone a repository…, paste its "
             "address, click Find, check what was found and click Clone this one. To give this computer a name of its own on GitHub: choose Name this computer (its GitHub identity)….",
     "must": [], "steps": True, "langs": ["en"]},
    {"id": "aicui_team_table", "windows": "using several AI assistants together on one project",
     "card": "The Team Table in AICUI: a table where several AIs work on one project together, like a meeting with "
             "a chair. Each seat is a model on this computer (free), a cloud model by your own key (paid as it "
             "works), or an outside agent such as Claude Code or Codex joining over a locked connection. One seat "
             "wears the crown: the lead plans, hands out the work and accepts or rejects it, and you are above it. "
             "Each file has one writer at a time, and the seats talk one at a time. To set it up: in AICUI, click "
             "the people icon at the right end of the box you type in, click a seat to choose who sits there (+ "
             "adds one), tick Wears the crown on the lead, click the paper in the middle for the session goals, "
             "then click Sit down.",
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
