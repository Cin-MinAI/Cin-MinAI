# SPDX-License-Identifier: GPL-3.0-or-later
<#
Automated boot test of the Cin-MinAI ISO in a throwaway Hyper-V VM (M1). Run on the dev PC, as a member of
"Hyper-V Administrators" (no elevation needed):

    powershell -ExecutionPolicy Bypass -File distro\vm-boottest.ps1 -Iso C:\path\cinminai-0.0.1-amd64-boottest.iso

The ISO must be the boot-test variant (BOOTTEST=1 distro/build-iso.sh): its menu starts the live system
after 5 s, and cinminai-boottest writes a report to COM1 once the desktop is up, then powers off. Hyper-V
can't type into Linux guests (M0 finding), so nothing here needs a keyboard.

The VM: generation 2 (UEFI), Secure Boot on with the Microsoft UEFI CA template (what real PCs use for
Linux), 4 GB RAM, 4 CPUs, no disk, no network. It's created fresh, and deleted afterwards whatever happens.
The M0 VMs (cinminai-uefi, cinminai-bios) are never touched. Exit code 0 = PASS.
#>
param(
    [Parameter(Mandatory)] [string] $Iso,
    [int] $TimeoutMinutes = 15,
    [string] $Name = 'cinminai-boottest',
    [string] $LogDir = "$env:USERPROFILE\cinminai-vm\boottest-logs"
)
$ErrorActionPreference = 'Stop'
if ($Name -in @('cinminai-uefi', 'cinminai-bios')) { throw "refusing to use the M0 VM name $Name" }
$Iso = (Resolve-Path $Iso).Path
if ($Iso -notmatch 'boottest') { throw "not a boot-test ISO (build it with BOOTTEST=1): $Iso" }
$pipe = "cinminai-boottest-$PID"
$vmDir = "$env:USERPROFILE\cinminai-vm\$Name"
New-Item -ItemType Directory -Force $LogDir | Out-Null
$log = Join-Path $LogDir ("{0:yyyy-MM-dd_HHmmss}.log" -f (Get-Date))
$lines = New-Object System.Collections.Generic.List[string]
$result = 'FAIL'

function Test-Vmms { (Get-Service vmms -ErrorAction SilentlyContinue).Status -eq 'Running' }

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
    New-VM -Name $Name -Generation 2 -MemoryStartupBytes 4GB -NoVHD -Path $vmDir | Out-Null
    Set-VMMemory -VMName $Name -DynamicMemoryEnabled $false
    Set-VMProcessor -VMName $Name -Count 4
    Set-VMFirmware -VMName $Name -EnableSecureBoot On -SecureBootTemplate MicrosoftUEFICertificateAuthority
    Add-VMDvdDrive -VMName $Name -Path $Iso
    Set-VMFirmware -VMName $Name -FirstBootDevice (Get-VMDvdDrive -VMName $Name)
    Get-VMNetworkAdapter -VMName $Name | Remove-VMNetworkAdapter      # offline, like a first live boot
    Set-VMComPort -VMName $Name -Number 1 -Path "\\.\pipe\$pipe"
    Set-VM -Name $Name -AutomaticCheckpointsEnabled $false

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
    $off = (Get-Date).AddSeconds(60)
    while ((Get-VM -Name $Name).State -ne 'Off' -and (Get-Date) -lt $off) { Start-Sleep 3 }
    if (Test-Vmms) { $lines.Add(("vm_state_after {0}" -f (Get-VM -Name $Name).State)) }
    else { $lines.Add("vmms stopped during the test (someone pressed Stop Service?) - the VM ran on unmanaged") }
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
