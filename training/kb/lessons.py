# SPDX-License-Identifier: GPL-3.0-or-later
"""Lesson cards v0: everyday computer basics and in-scope "boundary" questions, as help cards.

The transition knowledge base (transition.py) covers Windows habits -> Mint; the guide eval's lesson,
boundary and a few transition tasks came with their own cards, which were not in the knowledge base, so
at runtime `lookup_help` had nothing to find for them (found while building the daemon, 2026-09-28).
These cards carry the same facts as those eval cards, reworded to be general (no one task's details).
Same fields as transition.py. **To do before release:** check each fact again on Mint 22.3 in all six
languages, as was done for transition.py.
"""

TOPICS = [
    {"id": "copy_paste", "windows": "copying and pasting text",
     "card": "Copy and paste: select the text by holding the left mouse button and dragging over it. Right-click "
             "the selection and choose Copy (or press Ctrl+C). Click where it should go, right-click and choose "
             "Paste (or press Ctrl+V). Same keys as on Windows.",
     "must": [], "steps": True},
    {"id": "new_folder", "windows": "making a new folder to keep files tidy",
     "card": "New folder: open {files} and go to the place where the folder should be, for example Documents or "
             "Pictures in the left column. Right-click an empty spot, choose Create New Folder, type a name, and "
             "press Enter. Drag files onto the folder to move them in.",
     "must": ["files"], "steps": True},
    {"id": "usb_remove", "windows": "Safely Remove Hardware / ejecting a USB stick",
     "card": "Removing a USB stick: in {files}, find the stick in the left column and click the eject arrow next "
             "to its name. Wait until it disappears from the list, then pull it out.",
     "must": ["files"], "steps": True},
    {"id": "save_file", "windows": "saving a document (Ctrl+S, File > Save)",
     "card": "Saving: press Ctrl+S (or File > Save). The first time, choose a folder such as Documents, type a "
             "file name, and click Save. After that, Ctrl+S saves your changes to the same file.",
     "must": [], "steps": True},
    {"id": "files_folders", "windows": "what files and folders are",
     "card": "Files and folders: a file is one thing you keep, like a letter, a photo or a song. A folder is a box "
             "that holds files (and other folders) to keep them tidy. {files} shows both; folders have a folder "
             "icon.",
     "must": ["files"], "steps": False},
    {"id": "downloads", "windows": "finding downloaded files",
     "card": "Downloads: files from the web go to the Downloads folder. Open {files} and click Downloads in the "
             "left column. In {firefox} you can also click the arrow icon at the top-right to see recent "
             "downloads.",
     "must": ["files"], "steps": False},
    {"id": "zoom_text", "windows": "making text bigger in the browser and programs (Ctrl and +)",
     "card": "Bigger text: in {firefox} and most programs, hold Ctrl and press + to zoom in (Ctrl and - to zoom "
             "out, Ctrl and 0 to reset). For everything on the screen, open {accessibility} and switch on Large "
             "text.",
     "must": [], "steps": False},
    {"id": "right_click", "windows": "what right-clicking means",
     "card": "Right-click: press the right mouse button once. It opens a small menu of things you can do with "
             "what's under the pointer, like Copy, Rename or Open With. On a touchpad, tap with two fingers.",
     "must": [], "steps": False},
    {"id": "delete_files", "windows": "deleting files",
     "card": "Deleting files: in {files}, open the folder, select the files (Ctrl+A selects everything), then "
             "press Delete. Deleted files go to the Trash, so you can still get them back until you empty it.",
     "must": ["files"], "steps": True},
    {"id": "printers", "windows": "adding a printer (Devices and Printers)",
     "card": "Printers: most USB and network printers are found by themselves. If yours isn't, open {printers} "
             "from the Menu, click Add, choose your printer from the list, and click Forward to finish.",
     "must": ["printers"], "steps": True, "langs": ["en"]},
    {"id": "word_count", "windows": "counting the words in a Word document",
     "card": "Word count: in {writer}, the number of words is shown in the status bar at the bottom of the "
             "window. For details open Tools > Word and Character Count.",
     "must": ["writer"], "steps": False},
    {"id": "what_is_linux", "windows": "what Linux is, compared with Windows",
     "card": "What is Linux: Linux is the system that runs this computer, like Windows does on other computers. "
             "This computer uses Cin-MinAI, which is based on Linux Mint. It's free, it gets updates from "
             "{update_manager}, and it comes with programs for the web, email, letters, and photos.",
     "must": [], "steps": False},
    {"id": "dvd", "windows": "playing a DVD",
     "card": "DVDs: insert the DVD; it opens in {video_player}. Some store-bought DVDs need an extra part called "
             "libdvdcss: open {welcome} from the Menu, go to First Steps, and click Install Multimedia Codecs.",
     "must": ["video_player"], "steps": False},
    {"id": "chart", "windows": "making a chart in Excel",
     "card": "Charts: use {calc} (like Excel). Type your labels and amounts in two columns, select them, then "
             "choose Insert > Chart and click Finish.",
     "must": ["calc"], "steps": True},
    {"id": "video_call", "windows": "video calls (Zoom, Teams, Skype, WhatsApp)",
     "card": "Video calls: most video-call services (Zoom, Google Meet, Microsoft Teams, WhatsApp, Skype) work in "
             "{firefox}: open the link you were sent and allow the camera and microphone when asked. Zoom also "
             "has a program in {software_manager}.",
     "must": ["firefox"], "steps": False},
]
