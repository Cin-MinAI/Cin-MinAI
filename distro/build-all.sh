#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# All of it on the dev PC (Git Bash): llama.cpp (reused once built) -> packages + repo -> the real ISO +
# check-iso.sh -> the boot-test ISO -> the VM boot test. ~35 min (the first llama.cpp build adds ~40).
# Logs: /c/Users/Ian/cinminai-train-out/br-*.log (br-done.log sums up); boot-test logs and screenshots:
# /c/Users/Ian/cinminai-vm/boottest-logs/. Launch detached (docs/RESUME.md, "How to").
O=/c/Users/Ian/cinminai-train-out
W() { MSYS_NO_PATHCONV=1 wsl -d Ubuntu-24.04 "$@"; }
W -u root --cd /mnt/c/Users/Ian/Cin-minAI/distro -e bash build-llama.sh > $O/br-llama.log 2>&1 || { echo "LLAMA FAILED" > $O/br-done.log; exit 1; }
W --cd /mnt/c/Users/Ian/Cin-minAI/distro -e bash -c "bash build-packages.sh && bash make-repo.sh" > $O/br-pkgs.log 2>&1 || { echo "PKGS FAILED" > $O/br-done.log; exit 1; }
W -u root --cd /mnt/c/Users/Ian/Cin-minAI/distro -e bash -c "bash build-iso.sh && bash check-iso.sh" > $O/br-iso.log 2>&1; echo "iso+checks exit $?" > $O/br-done.log
W -u root --cd /mnt/c/Users/Ian/Cin-minAI/distro -e env BOOTTEST=1 bash build-iso.sh > $O/br-boottest-build.log 2>&1 || { echo "BOOTTEST BUILD FAILED" >> $O/br-done.log; exit 1; }
W -e cp /home/brickmii/cinminai-build/m1/out-test/cinminai-0.0.1-amd64-boottest.iso /mnt/c/Users/Ian/cinminai-vm/iso/
powershell.exe -ExecutionPolicy Bypass -NoProfile -File 'C:\Users\Ian\Cin-minAI\distro\vm-boottest.ps1' -Iso 'C:\Users\Ian\cinminai-vm\iso\cinminai-0.0.1-amd64-boottest.iso' > $O/br-vm.log 2>&1
echo "vm exit $?" >> $O/br-done.log
