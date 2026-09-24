#!/usr/bin/env bash
# Boot the spike ISO (or the installed disk) in QEMU/KVM. Window appears via WSLg.
#
#   ./vm.sh uefi|bios [iso|disk]      (in WSL: wsl -d Ubuntu-24.04 -u root -- ./vm.sh uefi)
#
# One disk per firmware so the BIOS and UEFI installs are tested independently.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
source "$here/config.env"
if [[ -n ${SUDO_USER:-} && $WORK == /root/* ]]; then WORK=$(getent passwd "$SUDO_USER" | cut -d: -f6)/cinminai-build; fi

fw=${1:?usage: vm.sh uefi|bios [iso|disk]}
boot=${2:-iso}
vm=$WORK/vm
disk=$vm/$fw.qcow2
mkdir -p "$vm"
[[ -f $disk ]] || qemu-img create -q -f qcow2 "$disk" 25G

args=(-enable-kvm -machine q35 -cpu host -smp 4 -m 6144
      -drive "file=$disk,if=virtio,format=qcow2"
      -nic user,model=virtio-net-pci
      -device virtio-vga -display gtk)
if [[ $fw == uefi ]]; then
    [[ -f $vm/OVMF_VARS.fd ]] || cp /usr/share/OVMF/OVMF_VARS_4M.fd "$vm/OVMF_VARS.fd"
    args+=(-drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd
           -drive "if=pflash,format=raw,file=$vm/OVMF_VARS.fd")
fi
[[ $boot == iso ]] && args+=(-cdrom "$WORK/out/$OUT_ISO" -boot once=d)
exec qemu-system-x86_64 "${args[@]}"
