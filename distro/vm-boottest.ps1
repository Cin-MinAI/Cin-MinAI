# SPDX-License-Identifier: GPL-3.0-or-later
<#
Automated boot test of the Cin-MinAI ISO in a throwaway Hyper-V VM (M1). Run on the dev PC, as a member of
"Hyper-V Administrators" (no elevation needed):

    powershell -ExecutionPolicy Bypass -File distro\vm-boottest.ps1 -Iso C:\path\cinminai-0.0.1-amd64-boottest.iso

The ISO must be the boot-test variant (BOOTTEST=1 distro/build-iso.sh): its menu starts the live system
after 5 s, and cinminai-boottest writes a report to COM1 once the desktop is up, then powers off. Hyper-V
can't type into Linux guests (M0 finding), so nothing here needs a keyboard.

The VM: generation 2 (UEFI), Secure Boot on with the Microsoft UEFI CA template (what real PCs use for
Linux), 8 GB RAM, 4 CPUs, no disk (with -Install: an empty 40 GB one), no network. It's created fresh, and deleted afterwards whatever happens.
The M0 VMs (cinminai-uefi, cinminai-bios) are never touched. Exit code 0 = PASS.
#>
param(
    [Parameter(Mandatory)] [string] $Iso,
    [int] $TimeoutMinutes = 30,
    [string] $Name = 'cinminai-boottest',
    [string] $LogDir = "$env:USERPROFILE\cinminai-vm\boottest-logs",
    # -Install: the install test (INSTALLTEST=1 ISO). An empty 40 GB disk is added; the ISO's first entry
    # installs onto it unattended and powers off; then the VM boots from that disk and the same report runs
    # in the installed system.
    [switch] $Install,
    [int] $InstallMinutes = 60
)
$ErrorActionPreference = 'Stop'
if ($Name -in @('cinminai-uefi', 'cinminai-bios')) { throw "refusing to use the M0 VM name $Name" }
$Iso = (Resolve-Path $Iso).Path
if ($Install -and $Iso -notmatch 'installtest') { throw "-Install needs the install-test ISO (INSTALLTEST=1): $Iso" }
if (-not $Install -and $Iso -notmatch 'boottest') { throw "not a boot-test ISO (build it with BOOTTEST=1): $Iso" }
$pipe = "cinminai-boottest-$PID"
$vmDir = "$env:USERPROFILE\cinminai-vm\$Name"
New-Item -ItemType Directory -Force $LogDir | Out-Null
$log = Join-Path $LogDir ("{0:yyyy-MM-dd_HHmmss}.log" -f (Get-Date))
$lines = New-Object System.Collections.Generic.List[string]
$result = 'FAIL'

function Test-Vmms { (Get-Service vmms -ErrorAction SilentlyContinue).Status -eq 'Running' }

function Save-ResultsScreenshot([string] $disk, [string] $png) {
    # header in the first 512 bytes: CINMINAI-SHOT, size, SHA-256; the PNG from byte 512
    try {
        if ((Get-VM -Name $Name).State -ne 'Off') { $lines.Add('screenshot: VM still running, results disk not read'); return }
        $fs = [IO.File]::OpenRead($disk)
        try {
            $head = New-Object byte[] 512; [void]$fs.Read($head, 0, 512)
            $h = [Text.Encoding]::ASCII.GetString($head).Split([char]10)
            if ($h[0] -ne 'CINMINAI-SHOT') { $lines.Add('screenshot: none on the results disk'); return }
            $size = [int]$h[1]; $sum = $h[2].Trim()
            $bytes = New-Object byte[] $size; $got = 0
            while ($got -lt $size) { $n = $fs.Read($bytes, $got, $size - $got); if ($n -le 0) { break }; $got += $n }
        } finally { $fs.Dispose() }
        $sha = [BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($bytes)).Replace('-', '').ToLower()
        if ($sha -eq $sum) { [IO.File]::WriteAllBytes($png, $bytes); $lines.Add("screenshot $png (verified)") }
        else { $lines.Add("screenshot damaged: checksum differs ($got of $size bytes read)") }
    } catch { $lines.Add("screenshot read failed: $($_.Exception.Message.Split([char]10)[0])") }
}

function Remove-TestVM {  # never throws: cleanup problems are reported, and the log is always written
    if (-not (Test-Vmms)) {
        $lines.Add("cleanup: Hyper-V's management service (vmms) isn't running - start it (Hyper-V Manager > Start Service), then delete $vmDir")
        return
    }
    try {
        $vm = Get-VM -Name $Name -ErrorAction SilentlyContinue
        if ($vm) {
            if ($vm.State -ne 'Off') { Stop-VM -Name $Name -TurnOff -Force -ErrorAction SilentlyContinue }
            Remove-VM -Name $Name -Force -ErrorAction Stop
        }
        if (Test-Path $vmDir) { Remove-Item -Recurse -Force $vmDir -ErrorAction Stop }
    } catch {
        $lines.Add("cleanup failed: $($_.Exception.Message.Split([char]10)[0]) - leftover: $vmDir")
    }
}

if (-not (Test-Vmms)) { throw "Hyper-V's management service (vmms) isn't running - start it in Hyper-V Manager (Start Service) first" }
try {
    Remove-TestVM   # a leftover from an interrupted run
    New-VM -Name $Name -Generation 2 -MemoryStartupBytes 8GB -NoVHD -Path $vmDir | Out-Null
    Set-VMMemory -VMName $Name -DynamicMemoryEnabled $false
    Set-VMProcessor -VMName $Name -Count 4
    Set-VMFirmware -VMName $Name -EnableSecureBoot On -SecureBootTemplate MicrosoftUEFICertificateAuthority
    Add-VMDvdDrive -VMName $Name -Path $Iso
    Set-VMFirmware -VMName $Name -FirstBootDevice (Get-VMDvdDrive -VMName $Name)
    Get-VMNetworkAdapter -VMName $Name | Remove-VMNetworkAdapter      # offline, like a first live boot
    Set-VMComPort -VMName $Name -Number 1 -Path "\\.\pipe\$pipe"
    if ($Install) {
        # the install target first, so it's /dev/sda (the preseed installs onto the first disk)
        $target = Join-Path $vmDir 'target.vhdx'
        New-VHD -Path $target -SizeBytes 40GB -Dynamic | Out-Null
        Add-VMHardDiskDrive -VMName $Name -Path $target
    }
    # an empty 32 MiB "results disk": the guest writes its screenshot onto it (a fixed VHD is the raw disk
    # plus a 512-byte footer, so it's read straight from the file afterwards; the serial port dropped bytes)
    $resultsDisk = Join-Path $vmDir 'results.vhd'
    New-VHD -Path $resultsDisk -SizeBytes 32MB -Fixed | Out-Null
    Add-VMHardDiskDrive -VMName $Name -Path $resultsDisk
    Set-VM -Name $Name -AutomaticCheckpointsEnabled $false

    if ($Install) {
        # phase 1: the unattended install; it powers the VM off when done
        $t0 = Get-Date
        Start-VM -Name $Name
        $until = $t0.AddMinutes($InstallMinutes)
        while ((Get-VM -Name $Name).State -ne 'Off' -and (Get-Date) -lt $until) { Start-Sleep 10 }
        if ((Get-VM -Name $Name).State -ne 'Off') { throw "the install didn't finish within $InstallMinutes min" }
        $lines.Add(('install_minutes {0:N1}' -f ((Get-Date) - $t0).TotalMinutes))
        # phase 2: boot the installed system from its disk, without the ISO
        Get-VMDvdDrive -VMName $Name | Set-VMDvdDrive -Path $null   # eject (removing the drive fails)
        Set-VMFirmware -VMName $Name -FirstBootDevice (Get-VMHardDiskDrive -VMName $Name | Where-Object Path -eq $target)
    }

    $start = Get-Date
    Start-VM -Name $Name
    $client = New-Object System.IO.Pipes.NamedPipeClientStream('.', $pipe, [System.IO.Pipes.PipeDirection]::In)
    $client.Connect(30000)
    $reader = New-Object System.IO.StreamReader($client)
    $deadline = $start.AddMinutes($TimeoutMinutes)
    $pending = $reader.ReadLineAsync()
    while ((Get-Date) -lt $deadline) {
        if (-not $pending.Wait(5000)) { continue }
        $line = $pending.Result
        if ($null -eq $line) { break }                                   # VM powered off, pipe closed
        $line = $line.Trim([char]13, [char]10, [char]0)
        if ($line) {
            $stamp = '{0,6:N0}s  {1}' -f ((Get-Date) - $start).TotalSeconds, $line
            $lines.Add($stamp); Write-Host $stamp
            if ($line -match '^CINMINAI-BOOTTEST RESULT (\w+)') { $result = $Matches[1] }
            if ($line -eq 'CINMINAI-BOOTTEST END') { break }
        }
        $pending = $reader.ReadLineAsync()
    }
    if ($lines.Count -eq 0 -or -not ($lines -match 'CINMINAI-BOOTTEST END')) {
        $lines.Add("no complete report within $TimeoutMinutes min - the live system didn't reach the desktop, or the report didn't run")
        $result = 'FAIL'
    }
    # give the guest a moment to power itself off (the report asks it to)
    $off = (Get-Date).AddSeconds(120)
    while ((Get-VM -Name $Name).State -ne 'Off' -and (Get-Date) -lt $off) { Start-Sleep 3 }
    if ((Get-VM -Name $Name).State -ne 'Off') {
        # the live system can take over a minute to shut down; the report has finished (and flushed the
        # results disk), so switching the VM off loses nothing
        $lines.Add('vm: still shutting down after 120 s - turned off')
        Stop-VM -Name $Name -TurnOff -Force
    }
    if (Test-Vmms) { $lines.Add(("vm_state_after {0}" -f (Get-VM -Name $Name).State)) }
    else { $lines.Add("vmms stopped during the test (someone pressed Stop Service?) - the VM ran on unmanaged") }
    Save-ResultsScreenshot $resultsDisk ($log -replace '\.log$', '-desktop.png')
}
catch {
    $lines.Add("runner error: $($_.Exception.Message)")
    $result = 'FAIL'
}
finally {
    try { if ($reader) { $reader.Dispose() }; if ($client) { $client.Dispose() } } catch { }
    Remove-TestVM
    $lines.Insert(0, "iso $Iso")
    $lines.Add("RESULT $result")
    $lines | Set-Content -Encoding utf8 $log   # always written, whatever happened above
    Write-Host "RESULT $result  (log: $log)"
}
if ($result -eq 'PASS') { exit 0 } else { exit 1 }
