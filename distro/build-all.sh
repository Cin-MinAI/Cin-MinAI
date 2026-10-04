#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# All of it on the dev PC (Git Bash): llama.cpp (reused once built) -> packages + repo -> the real ISO +
# check-iso.sh -> the boot-test ISO -> the VM boot test -> the install-test ISO -> the VM install test.
# ~60 min (INSTALL=0: ~35; the first llama.cpp build adds ~40).
# Logs: /c/Users/Ian/cinminai-train-out/br-*.log (br-done.log sums up); boot-test logs and screenshots:
# /c/Users/Ian/cinminai-vm/boottest-logs/. Launch detached (docs/RESUME.md, "How to").
O=/c/Users/Ian/cinminai-train-out
W() { MSYS_NO_PATHCONV=1 wsl -d Ubuntu-24.04 "$@"; }
W -u root --cd /mnt/c/Users/Ian/Cin-minAI/distro -e bash build-llama.sh > $O/br-llama.log 2>&1 || { echo "LLAMA FAILED" > $O/br-done.log; exit 1; }
W -u root --cd /mnt/c/Users/Ian/Cin-minAI/distro -e bash build-whisper.sh > $O/br-whisper.log 2>&1 || { echo "WHISPER FAILED" > $O/br-done.log; exit 1; }
W --cd /mnt/c/Users/Ian/Cin-minAI/distro -e bash -c "bash build-packages.sh && bash make-repo.sh" > $O/br-pkgs.log 2>&1 || { echo "PKGS FAILED" > $O/br-done.log; exit 1; }
W -u root --cd /mnt/c/Users/Ian/Cin-minAI/distro -e bash -c "bash build-iso.sh && bash check-iso.sh" > $O/br-iso.log 2>&1; echo "iso+checks exit $?" > $O/br-done.log
W -u root --cd /mnt/c/Users/Ian/Cin-minAI/distro -e env BOOTTEST=1 bash build-iso.sh > $O/br-boottest-build.log 2>&1 || { echo "BOOTTEST BUILD FAILED" >> $O/br-done.log; exit 1; }
W -e cp /home/brickmii/cinminai-build/m1/out-test/cinminai-0.0.1-amd64-boottest.iso /mnt/c/Users/Ian/cinminai-vm/iso/
# WSL keeps the memory the builds used (~13 GB); with the 8 GB test VM on top, Windows ran out on
# 2026-09-28 and Claude Code stopped the run. Hand it back before any VM starts (WSL restarts on demand).
wsl.exe --shutdown
powershell.exe -ExecutionPolicy Bypass -NoProfile -File 'C:\Users\Ian\Cin-minAI\distro\vm-boottest.ps1' -Iso 'C:\Users\Ian\cinminai-vm\iso\cinminai-0.0.1-amd64-boottest.iso' > $O/br-vm.log 2>&1
echo "vm exit $?" >> $O/br-done.log
# the install test: unattended install onto an empty VM disk, then the report from the installed system
# (INSTALL=0 skips it; ~25 min)
if [[ ${INSTALL:-1} == 1 ]]; then
    W -u root --cd /mnt/c/Users/Ian/Cin-minAI/distro -e env INSTALLTEST=1 bash build-iso.sh > $O/br-installtest-build.log 2>&1 || { echo "INSTALLTEST BUILD FAILED" >> $O/br-done.log; exit 1; }
    W -e cp /home/brickmii/cinminai-build/m1/out-test/cinminai-0.0.1-amd64-installtest.iso /mnt/c/Users/Ian/cinminai-vm/iso/
    wsl.exe --shutdown
    powershell.exe -ExecutionPolicy Bypass -NoProfile -File 'C:\Users\Ian\Cin-minAI\distro\vm-boottest.ps1' -Install -Iso 'C:\Users\Ian\cinminai-vm\iso\cinminai-0.0.1-amd64-installtest.iso' > $O/br-install.log 2>&1
    echo "install exit $?" >> $O/br-done.log
fi
