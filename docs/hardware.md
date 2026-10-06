# Hardware notes — what the assistant can't see

The assistant can help with most software problems: it reads the system's own records and explains what it
finds. But when the screen is black, it can't help you at all — so the hardware lessons live here, on a page you
can open from your phone. Like building a PC, **your hardware decides the order you have to do things in.**

Everything below happened on our own machines. Tell us yours (see [HELP-WANTED](HELP-WANTED.md)) and we'll add it.

## Giving the whole graphics card to the AI (use the motherboard's video output)

**Why:** the desktop takes some of the graphics card's memory. If your processor has graphics built in, you can
plug the monitor into the **motherboard** instead, and the card's memory goes entirely to the AI. On our test PC
(GTX 1080 Ti, i7-4790K) the desktop used about 480 MB of the card; after the change it used 7 MB, and the large
27B model fit entirely on the card with room for long conversations — about 13–14 words per second instead of 8½.

**First check:** your processor needs built-in graphics, and your motherboard needs a video port (HDMI,
DisplayPort, DVI or VGA on the back panel). Intel processors with an "F" in the name (like i5-12400F) and most
AMD Ryzen processors without a "G" have none — then this change isn't possible.

**Do it in this order** — the order matters:

1. **Leave the monitor cable in the graphics card** for now.
2. **Restart and open the BIOS** (the setup screen): usually by pressing **Delete** or **F2** right as the PC
   starts. The first screen often says which key.
3. **Find the setting for which graphics starts first.** Its name depends on the motherboard maker: on our
   Gigabyte board it's **Init Display First**; others call it *Primary Display*, *Primary Video Adapter* or
   *IGD/iGPU*. Set it to the **onboard / integrated / IGFX** option. If there's a setting to keep the built-in
   graphics on when a card is installed (*IGD Multi-Monitor*, *iGPU Multi-Monitor*), turn that on too.
4. **Save and exit** (often **F10**). Let the PC shut down or restart.
5. **Now move the monitor cable** from the graphics card to the motherboard's video port. (Turning the PC off
   first is the calm way to do it.)
6. **Start the PC.** The BIOS screen and the desktop now appear on the motherboard's output, and the graphics card
   is free for the AI.

**What goes wrong in the other order** (this happened to us): if you move the cable to the motherboard *first*,
it can seem to work — until the next restart. With a graphics card installed, many motherboards start on the
**card** by default, so after a restart there's **no picture at all, not even the BIOS**. Nothing is broken.
**To get back:** put the cable back in the graphics card, start the PC, open the BIOS, change the setting
(step 3), save, and only then move the cable to the motherboard.

**To undo:** cable back in the graphics card, BIOS, set the first display back to the card (often called *PEG*,
*PCIe* or *Auto*), save, restart.

## No picture after starting from the USB stick (NVIDIA cards)

Cin-MinAI's first menu entry keeps the open-source NVIDIA driver (*nouveau*) switched off, because on some
cards it leaves the screen black or freezes the desktop. If you still get a black screen, restart and pick the
menu entry for **compatibility mode**. Once installed, the assistant can help you set up NVIDIA's own driver
(Driver Manager).

**Older NVIDIA cards (GTX 900 and 10 series, like the 1060, 1070 and 1080 Ti):** NVIDIA's 580 driver is the last
one that supports them. Driver Manager recommends it; don't move to a newer driver series on these cards.

## Freezes or failed writes after a kernel update (older disks)

A newer Linux kernel isn't always better for older hardware. On our test PC, kernel 7.0 made an older SATA SSD's
connection fail under load (freezes, failed writes), and the NVIDIA driver failed to start; the long-term kernel
had none of it. The assistant's computer check spots this pattern and says what to do — if you can still see the
screen: **Update Manager → View → Linux kernels**, install the **long-term** kernel series (6.8 on this release),
and remove the one that causes trouble. If the desktop won't start at all, restart, open **Advanced options** in
the boot menu, and pick the older kernel from there.

## Where to keep your AI models (the faster the drive, the faster the answers)

AI models are big files, and the bigger ones don't fit in your computer's memory all at once — so while the
assistant works, it keeps reading pieces of the model from the drive. **The kind of drive it's on changes how fast
it answers**, sometimes by a lot. From fastest to slowest:

1. **NVMe drive** — a small stick-shaped drive plugged straight into the motherboard (or an adapter card). The best
   place for models.
2. **SSD** (SATA) — a solid-state drive connected with a cable. Good.
3. **Hard disk** (HDD) — a spinning disk inside the PC. Fine for storing, slow for running a big model.
4. **USB drive** — anything plugged into a USB port. Slowest to run from, but a great place to **park** models you
   aren't using: when you want one back, the system copies it to your fast drive — much quicker than downloading it
   again (on our test PC: about 10 minutes for 79 GB, where the download took about an hour).

**Not sure which drives you have?** Ask the assistant ("what drives does my computer have?"), or open **Disks**
from the menu.

**Measured on our test PC** (2014 i7-4790K, 32 GB memory, GTX 1080 Ti) with Qwen3.8-Flash-Next, a very large model
(125B) that only fits by keeping most of itself on the drive:

| Where the model was | Start-up | Writing, once warmed up | Reading a long text |
|---|---|---|---|
| USB hard disk | 4 min 09 s | about 2 | about 4½ |
| One third on a SATA SSD, the rest on the USB disk | 2 min 12 s | 2¼ – 2¾ | about 6½ |
| NVMe | *measuring now* | | |

(Speeds are in tokens — pieces of words — per second. Smaller models that fit in memory barely care where they're
stored, once loaded.)

**Network storage** (a NAS, a shared folder on another computer) can hold and even run models — how fast depends on
the network and the drives behind it — but getting a good experience takes a lot more setup and a lot more hardware.
Not where to start.

## Starting from the USB stick

To start from the stick, most PCs have a **boot menu key** you press right as the PC starts — often **F12**,
**F11**, **F8** or **Esc** (the first screen often says which). Pick the USB stick there. Your own disks aren't
touched until you choose to install. How to make the stick: [make-usb-stick.md](install/make-usb-stick.md).
