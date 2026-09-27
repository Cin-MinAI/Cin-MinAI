# Make your Cin-MinAI USB stick

You'll turn a USB stick into a Cin-MinAI starter. With it you can try Cin-MinAI on your computer
without changing anything, and install it when you're ready. It takes about 15 minutes, most of it
waiting. You don't need to type any commands.

*Screenshots will be added with the first public download.*

## What you need

- **A USB stick of 8 GB or more.** Everything on it will be erased, so copy off anything you want to
  keep first.
- **The Cin-MinAI file** (it ends in `.iso` and is a few gigabytes) from the download page. Leave the download page
  open: it shows a long number called the **SHA-256** that you'll use to check the file.
- **A Windows computer** to make the stick (on a Mac, see the end of this page).

## 1. Download a writing program

Pick one. Both are free and trusted by millions of people.

- **balenaEtcher** — the simplest. Three buttons. Download it from **etcher.balena.io** and install it.
- **Rufus** — small, no installation needed, and it can check your download. Download it from
  **rufus.ie** and open it.

## 2. Check your download (recommended)

This makes sure the file arrived complete and is really ours.

**With Rufus:** open Rufus, click **SELECT** and choose the Cin-MinAI file. Then click the small
**tick (✓) button** next to SELECT. After a moment Rufus shows three long numbers; compare the one next
to **SHA256** with the number on the download page. They must match exactly. The first and last six
characters are usually enough to compare by eye.

**With Etcher:** Etcher checks the stick after writing, but not the download itself. If the file didn't
download completely, Etcher will usually refuse it.

If the numbers don't match, download the file again.

## 3. Write the stick

Plug in the USB stick.

**With balenaEtcher:**
1. Click **Flash from file** and choose the Cin-MinAI file.
2. Click **Select target** and choose your USB stick. Check that it's the right one by its name and size.
3. Click **Flash!** and wait. Windows may ask if Etcher may make changes: click **Yes**.
4. Etcher writes the stick, then checks it. When it says **Flash Complete!**, you're done.

**With Rufus:**
1. Under **Device**, choose your USB stick.
2. Click **SELECT** and choose the Cin-MinAI file (already done if you checked the download).
3. Leave the other settings as they are and click **START**.
4. Rufus asks how to write the image: choose **Write in DD Image mode** and click **OK**. This makes an
   exact copy of the file, which is what we test.
5. Rufus warns that everything on the stick will be erased: click **OK**. When the bar says **READY**,
   you're done.

**If Windows says "You need to format the disk before you can use it", click Cancel.** That's normal:
Windows can't read the stick's new format, but your computer can start from it. Formatting would erase
what you just wrote.

## 4. Start your computer from the stick

Leave the stick plugged in.

**The easy way, from Windows 10 or 11:**
1. Open **Settings** → **Update & Security** (Windows 11: **System**) → **Recovery**.
2. Under **Advanced startup**, click **Restart now**.
3. Choose **Use a device**, then your USB stick.

**Or with a key while the computer starts:** switch it on and press the boot-menu key a few times
right away. It's often shown on the first screen for a moment. Common keys: **F12** (Dell, Lenovo,
Acer, Gigabyte), **F11** (MSI, ASRock), **F8** (ASUS desktops), **Esc** or **F9** (HP), **Esc** (many
ASUS laptops). Then choose the USB stick from the list.

When the menu appears, choose the first option and wait. After a minute or two you'll see the
Cin-MinAI desktop.

## 5. Try it, then install

You're now running Cin-MinAI from the stick. Nothing on your computer has changed. Look around; the
assistant works here too, but more slowly, because it has to use the processor instead of your
graphics card.

When you're ready, double-click **Install** on the desktop. Installed, Cin-MinAI starts faster, the
assistant answers in seconds, and your files and settings are kept. We recommend installing on an
**SSD**; an **M.2 NVMe** drive is ideal.

## If something doesn't work

- **The computer starts Windows as usual.** It didn't start from the stick: use "the easy way" in
  step 4, or try a different boot-menu key. On some computers the stick only appears in a USB port
  directly on the computer, not on a hub or a keyboard.
- **"Secure Boot violation" or a similar message.** Cin-MinAI works with Secure Boot switched on. If
  you still see this, write the stick again with Etcher, or with Rufus in DD Image mode.
- **A black screen after choosing the first option.** Restart, and choose **compatibility mode** from
  the menu instead.
- **Still stuck?** Ask the project for help (the download page links to where); tell us your computer's make and model.

## Getting your USB stick back afterwards

After Cin-MinAI is written, Windows may show the stick as very small or not at all. To use it for files
again: open **Rufus**, choose the stick, set **Boot selection** to **Non bootable**, and click **START**.
Or, in Windows: right-click the **Start** button → **Disk Management** → right-click each part of the
USB stick → **Delete Volume**; then right-click the empty space → **New Simple Volume** → **Next**
until done.

## On a Mac, or on Linux

- **Mac:** use **balenaEtcher**, the same three steps as above. To start from the stick, restart while
  holding the **Option (⌥)** key and choose the USB stick (Intel Macs; Apple silicon Macs can't start
  Cin-MinAI).
- **Linux Mint** (or another Cin-MinAI computer): right-click the file → **Make bootable USB stick**, or
  open **USB Image Writer** from the menu.

---

*This guide is part of Cin-MinAI and is published under CC BY-SA 4.0. Improvements are welcome.*
