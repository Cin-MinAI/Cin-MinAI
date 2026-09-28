# An NVIDIA edition of the ISO — licence notes

*Written 2026-09-28 by Claude (lead) for Ian's decision on option (b) of the 4K/NVIDIA question (boot check 1:
the live USB needed "compatibility mode" on the Mint box's 4K TV, because the open nouveau driver can't drive
the 1080 Ti there). These are reading notes, not legal advice: before a wide public release, someone
qualified should check them.*

**Sources, read on the Mint box (installed Mint 22.3):** `/usr/share/doc/nvidia-driver-580/copyright`
(package `nvidia-driver-580` 580.178.04-0ubuntu0.24.04.1: the NVIDIA Driver License Agreement, NVIDIA's
README note and an NVIDIA email, all quoted there) and `/usr/share/doc/libcublas12/copyright` (CUDA 12.0
from Ubuntu: the CUDA Toolkit licence and its Attachment A).

## What an NVIDIA edition would carry

Ubuntu's NVIDIA 580 driver packages, unchanged, so the live USB and the installed system get the GPU
(and our CUDA module, `cinminai-llama-cuda`) from the first boot. 580 is the branch that still supports
Pascal (the 1080 Ti) and covers newer cards too.

## Findings

1. **Distribution is allowed — on two conditions.** Licence §1.1(d): you may "distribute the SOFTWARE
   provided for use with operating system kernels distributed under the terms of an OSI-approved open
   source license …, provided that (i) the binary files thereof are not modified in any way (except for
   uncompressing of compressed files) and (ii) this Agreement is provided to each SOFTWARE recipient."
   Ubuntu's packages satisfy (ii) with their `copyright` file; we'd keep it and also put the licence on
   the ISO and the download page. NVIDIA's README, quoted in the package: "Linux distributions are welcome
   to repackage and redistribute the NVIDIA Linux driver in whatever package format they wish."
2. **Prebuilt kernel modules: NVIDIA says it's fine.** An NVIDIA email in the package answers a Debian
   maintainer asking whether distributing "binary kernel modules compiled from the NVIDIA kernel module
   source" is permitted: "This is fine; thanks for asking."
3. **The GPL question depends on the card.** The *open* kernel modules (`kernel-open`) are MIT, and "when
   linked together to form a Linux kernel module, the resulting Linux kernel module is dual licensed as
   MIT/GPL-2" — no question there, but they need Turing (GTX 16xx / RTX 20xx) or newer. **Pascal and Maxwell
   need the proprietary module**, which is the long-debated case: a closed module loaded into a GPL kernel.
   Canonical ships such modules prebuilt; Debian declines to. Licence §2.9 also says you may not use the
   software "in any manner that would cause it to become subject to an open source software license".
   Shipping Ubuntu's separate, unmodified packages follows Canonical's practice; it's a stance we'd take on
   purpose and write down.
4. **Secure Boot decides which packaging.** A kernel module must be signed to load with Secure Boot on.
   Canonical's prebuilt modules are signed with its key and load under shim with no user step. **DKMS**
   modules are compiled on the user's machine and need a key enrolled (a blue MOK screen at the next boot) —
   and the Mint box itself has `nvidia-dkms-580` (what Driver Manager chose there), so "what Mint installs"
   isn't automatically the Secure-Boot-friendly option. For an ISO we'd want Canonical's signed prebuilt
   modules for the ISO's exact kernel (Mint 22.3: 6.14.0-37). **Verified 2026-09-28** in Ubuntu's archive
   (snapshot 20260927): `linux-modules-nvidia-580-6.14.0-37-generic` 6.14.0-37.37~24.04.1+2, with
   Canonical's signatures in `linux-signatures-nvidia-6.14.0-37-generic`. (The kernel on the ISO and these
   modules must move together: pinning both is part of the build, like the rest.)
5. **Terms the user agrees to.** The licence is "PLEASE READ AND AGREE BEFORE USING". Among its terms: the
   licence is "revocable" (§1.1); GeForce/Titan software "is licensed for use only on GeForce or Titan
   hardware products you own" and "is not licensed for datacenter deployment" (§2.8); no reverse
   engineering or modification of the binaries (§2.2, §2.3); and the user indemnifies NVIDIA for use of
   products built with it (§2.11). Ubuntu installs it with no click-through. For our audience (Rule 9:
   offered, never imposed) the edition's download page and first boot should say in plain words that it
   contains NVIDIA's own licensed driver, with a link to the licence.
6. **CUDA libraries have a stricter condition.** cuBLAS and the CUDA runtime are listed as redistributable
   (Attachment A: "libcublas.so, libcublasLt.so …", "libcudart.so …"), but distribution comes with
   requirements (§1.1.2): the application must have "material additional functionality" (ours does), and
   "the distributable portions of the SDK shall only be accessed by your application". Installed as
   Ubuntu's system-wide `libcublas12` packages *from Ubuntu's archive*, they're Ubuntu's distribution, not
   ours; **put on our ISO**, that second condition fits poorly. Options: fetch them from Ubuntu's archive at
   install/first boot rather than putting them on the ISO, or bundle a private copy inside
   `cinminai-llama-cuda` used only by our llama-server. To decide with the review.
7. **Names.** "NVIDIA" and "GeForce" used only to describe compatibility ("for NVIDIA graphics cards"),
   never a logo or anything suggesting endorsement.
8. **Our own rules.** Non-free software on our ISO: a section in `LICENSING.md`; a separate, clearly named
   download ("Cin-MinAI 0.x — NVIDIA edition"), offered next to the standard one, never the default (Rule 9,
   D26). The standard ISO stays free of it.

## What this means for the choice

Option (b) looks permitted, with work: unmodified Ubuntu packages, the licence shipped and shown, signed
prebuilt modules for Secure Boot, the CUDA libraries kept off the ISO (or private to our app), and a written
stance on the proprietary module for Pascal/Maxwell. Options (a) — name the safe-graphics entry plainly —
and (c) — the driver at first boot through the admin boundary (M5) — need none of this and can ship with the
standard ISO in any case. The three aren't exclusive: (a) now, (c) in M5, (b) as an offered extra if the
review agrees.
