# Dual-Panel Linux AI Workspace — Original Specification

> This is the original design specification, kept verbatim for reference.
> Section numbers (§N) are cited from [PLAN.md](PLAN.md), which records the
> decisions and amendments made since. **Where the two disagree, PLAN.md wins.**

## 1. Project Goal

Build a lightweight, local-first Linux development environment for Linux Mint/Cinnamon that combines:

* A real interactive Linux terminal.
* A locally running Qwen coding assistant.
* Linux system and hardware awareness.
* Optional live web research.
* Firefox-to-terminal context transfer.
* Controlled execution of AI-proposed commands.
* Explicit human permission for administrator-level and hardware-writing operations.
* Hardware-sensitive model configuration suitable for older NVIDIA GPUs, especially Pascal-generation cards such as the GTX 1070 8GB and GTX 1080 Ti 11GB.
* Future support for a Linux/hardware-specialized LoRA covering system administration, embedded development, hardware buses, microcontrollers, and HDL workflows.

The application should feel like a small native Linux tool, not a heavyweight IDE.

The central idea is:

```text
Human Terminal + Local AI + Linux Context + Hardware Context
```

The AI should be able to investigate the machine, reason about problems, inspect source code, compile/test software, research documentation, and propose solutions.

It must not silently gain administrator control or perform privileged hardware writes.

---

# 2. Fundamental Design Principles

The implementation should preserve the following rules throughout the project.

### Rule 1 — Local first

The language model runs locally.

Normal source code, terminal output, logs, system information, and project files stay local unless the user deliberately invokes a web-related feature.

The application should remain useful with the network disconnected.

### Rule 2 — The terminal is real

Do not simulate Bash by spawning a fresh shell process for every command.

The terminal should use a persistent PTY so that normal Linux shell behavior survives:

```text
cd
export
aliases
shell functions
virtualenv activation
ssh
gdb
python REPL
job control
Ctrl-C
Ctrl-Z
interactive commands
```

Interactive programs such as `vim`, `top`, `htop`, `less`, `nano`, and GDB require actual terminal emulation rather than a simple scrolling log.

Textual supports concurrent workers and is appropriate for keeping subprocess/model/network work from blocking the UI. ([Textual Documentation][1])

A third-party PTY terminal widget can be evaluated, but terminal integration should be hidden behind our own interface so that it can be replaced later. Existing projects demonstrate that Textual can host real PTY-backed terminal emulators. ([GitHub][2])

### Rule 3 — Model output is not authorization

This must remain true everywhere:

```text
MODEL REQUEST ≠ USER PERMISSION
```

Qwen is allowed to propose actions.

Qwen is not allowed to grant itself administrator privileges.

### Rule 4 — Human has the dangerous button

Administrator actions and hardware-writing operations must visibly stop for user authorization.

The user must see what will be executed.

There must always be a Deny option.

### Rule 5 — Do not give Qwen a privileged shell

Never implement:

```text
sudo bash
sudo -s
sudo su
persistent root token
five-minute unrestricted sudo session
```

Instead:

```text
Qwen
 ↓
requests one privileged action
 ↓
permission dialog
 ↓
human approves
 ↓
privileged helper performs that action
 ↓
privilege disappears
```

### Rule 6 — Inspection before modification

The Linux/hardware assistant should be trained and prompted around:

```text
observe
   ↓
identify
   ↓
form hypothesis
   ↓
inspect/test
   ↓
propose change
   ↓
human authorization if needed
   ↓
change
   ↓
verify
```

Avoid:

```text
symptom
 ↓
guess
 ↓
sudo something
 ↓
hope
```

---

# 3. Target Platform

Initial supported platform:

```text
Linux Mint Cinnamon
Ubuntu/Debian-family base
x86-64
Python 3.11+
NVIDIA optional
```

Primary hardware targets:

| Class   | Typical GPU       |       VRAM | Intended model                        |
| ------- | ----------------- | ---------: | ------------------------------------- |
| Legacy  | GTX 1070          |       8 GB | Qwen Coder 3B or experimentally 7B Q4 |
| Legacy+ | GTX 1080 Ti       |      11 GB | Qwen Coder 7B Q4/Q5                   |
| Modern  | RTX / 12 GB+      |     12+ GB | Configurable                          |
| CPU     | No compatible GPU | system RAM | Smaller quantized model               |

Do not hard-code behavior solely from GPU names.

Hardware fingerprinting should produce a candidate configuration and then perform an actual inference test.

---

# 4. Model Architecture

## Base model

Initial preferred family:

```text
Qwen2.5-Coder-Instruct
```

Qwen2.5-Coder covers 92 programming languages and supports up to 128K context at the model level. ([Qwen][3])

The application should **not** attempt to use 128K on small Pascal GPUs.

Deployment context should be chosen based on available memory and actual benchmarking.

Suggested defaults:

```text
8 GB VRAM:
    4096 tokens
    optionally 8192 after validation

11 GB VRAM:
    8192 tokens
    optionally 16384 after validation

larger GPU:
    dynamically benchmark
```

The context length should be configurable.

---

# 5. Inference Backend Abstraction

Do not couple the application directly to Ollama internals.

Create:

```python
class InferenceBackend:
    async def generate(...)
    async def stream(...)
    async def health(...)
    async def model_info(...)
    async def unload(...)
```

Implement:

```text
OllamaBackend
LlamaCppBackend
```

Start with Ollama if it produces the simplest installation experience.

Keep llama.cpp support because it offers lower-level configuration and direct runtime LoRA support. Current llama.cpp server tooling can load LoRA adapters using `--lora` and can control adapters dynamically. ([GitHub][4])

This allows the project eventually to support:

```text
stock Qwen
stock Qwen + Linux LoRA
stock Qwen + hardware LoRA
merged custom model
```

without rewriting the UI.

---

# 6. Quantization and Memory Management

Model weights should normally use:

```text
Q4_K_M
```

with:

```text
Q5_K_M
```

available where VRAM permits.

Do not promise a particular tokens-per-second rate.

Measure it.

The installer should report:

```text
GPU
VRAM
model
quantization
context
prompt processing rate
generation rate
estimated remaining VRAM
```

Ollama currently exposes KV cache configuration through `OLLAMA_KV_CACHE_TYPE`; its documentation describes `q8_0` as using approximately half the memory of `f16`, with a small precision tradeoff. ([GitHub][5])

However, support depends on the selected model architecture/backend/device.

Therefore:

```text
DO NOT blindly force q8_0.
```

Instead:

```text
attempt preferred configuration
        ↓
start test model
        ↓
verify initialization
        ↓
run short generation benchmark
        ↓
retain or fall back
```

Possible fallback sequence:

```text
Q5 model + preferred KV
↓
Q4 model + preferred KV
↓
Q4 model + default KV
↓
reduce context
↓
smaller model
```

---

# 7. Hardware Fingerprinting

`install.sh` or the first-run configurator should inspect:

```bash
uname -a
cat /etc/os-release
lscpu
free -h
nvidia-smi
lspci -nn
```

Where available also obtain:

```text
GPU model
driver version
VRAM total
VRAM free
system RAM
CPU thread count
disk space
CUDA/runtime visibility
Ollama presence
llama.cpp presence
```

Produce a configuration file such as:

```toml
[hardware]
gpu_vendor = "nvidia"
gpu_model = "GeForce GTX 1080 Ti"
vram_mb = 11264
ram_mb = 32768

[inference]
backend = "ollama"
model = "qwen2.5-coder:7b"
context = 8192
kv_cache = "auto"
```

The configuration should remain editable.

---

# 8. TUI Layout

The main interface should be approximately:

```text
┌──────────────────────────────────────────────────────────────────┐
│ QWEN WORKSPACE                   GPU: 9.1/11 GB     ctx: 8192    │
├───────────────────────────────┬──────────────────────────────────┤
│                               │                                  │
│        LINUX TERMINAL         │        QWEN ASSISTANT            │
│                               │                                  │
│ $ make                        │  Build failed in parser.cpp.     │
│ ...                           │                                  │
│                               │  Likely cause: ...               │
│                               │                                  │
│                               │  Suggested command:              │
│                               │  $ grep -R ...                   │
│                               │                                  │
│                               │  [COPY] [RUN] [EXPLAIN]          │
│                               │                                  │
├───────────────────────────────┴──────────────────────────────────┤
│ /web /man /git /file /usb /pci /hw             LOCAL ● WEB ○   │
└──────────────────────────────────────────────────────────────────┘
```

Use Textual for:

```text
layout
focus
input handling
scrolling
dialogs
status information
AI response rendering
approval dialogs
```

---

# 9. Left Panel — Real Terminal

The left panel should be an actual persistent PTY.

Conceptually:

```text
Textual TerminalWidget
        │
        ▼
PTY master
        │
        ▼
/bin/bash
```

The terminal process should inherit:

```text
HOME
PATH
TERM
current user
interactive shell configuration
```

The PTY must handle terminal resize events.

Avoid using `asyncio.create_subprocess_shell()` as the only shell implementation because it cannot properly maintain interactive shell state.

## Terminal abstraction

Create something like:

```python
class TerminalSession:
    start()
    write(data)
    resize(cols, rows)
    interrupt()
    read()
    close()
```

The UI should not need to care whether this is implemented through:

```text
pty + pyte
textual-terminal
textual-tty
custom terminal emulator
```

That allows experimentation without coupling the project to a young third-party terminal widget.

---

# 10. Human Shell vs AI Execution

The user's interactive Bash session and Qwen's execution environment should be conceptually separate.

Recommended:

```text
LEFT PANEL
real human shell

AI TOOL EXECUTION
restricted agent process
```

Qwen should not simply type invisible commands into the human PTY.

When Qwen proposes a command:

```text
[ COPY ]
[ SEND TO TERMINAL ]
[ RUN IN AI WORKSPACE ]
[ EXPLAIN ]
```

`SEND TO TERMINAL` should preferably place the command at the prompt without automatically submitting Enter.

This keeps the distinction obvious:

```text
suggestion ≠ execution
```

---

# 11. AI Workspace

Give Qwen an execution area designed for autonomous experimentation.

Suggested location:

```text
~/.local/share/qwen-workspace/workspaces/
```

Projects explicitly opened for Qwen can live here or be made available through a project manager.

Qwen may autonomously:

```text
create files
edit source
compile
run tests
inspect logs
run normal development tools
perform Git diffs
use language servers
```

inside its designated workspace.

Avoid letting autonomous tools wander across all of `$HOME` by default.

This adds substantial safety without complicating the user interface.

---

# 12. Permission System

Keep this intentionally simple.

Two normal classes are sufficient for v1:

```text
NORMAL
ADMIN / HARDWARE WRITE
```

### Normal operation

Allowed without administrator authorization:

```text
read system state
read project files
compile
run tests
inspect USB
inspect PCI
inspect processes
inspect logs available to user
query manpages
Git operations inside project
network queries initiated through configured tools
```

### Permission-required operation

Examples:

```text
sudo-required command
package installation
system package removal
writing /etc
modifying protected system files
system-wide service changes
mount changes
boot configuration
kernel-module installation/removal
partition changes
filesystem formatting
raw block writes
firmware flashing
EEPROM writes
PCI configuration writes
raw MMIO access
BIOS/UEFI modification
```

The system should present:

```text
┌──────────────────────────────────────────────────────┐
│ ADMINISTRATOR PERMISSION REQUIRED                    │
│                                                      │
│ Qwen proposes:                                       │
│                                                      │
│ systemctl restart bluetooth.service                  │
│                                                      │
│ Reason: Apply the configuration change and verify    │
│ whether the Bluetooth controller initializes.        │
│                                                      │
│ [ DENY ]                              [ APPROVE ]     │
└──────────────────────────────────────────────────────┘
```

Approval should authorize **that operation once**.

No permanent approval option is necessary for v1.

---

# 13. Polkit Integration

Use Linux's existing privilege system rather than inventing authentication.

Polkit is explicitly designed around an unprivileged subject requesting that a privileged mechanism perform an operation, with an authorization authority deciding whether to allow it. That closely matches this project's architecture. ([Polkit][6])

Architecture:

```text
Qwen/TUI
   │
   │ structured request
   ▼
qwen-admin-helper
   │
   ▼
Polkit authorization
   │
   ▼
Cinnamon authentication dialog
   │
   ▼
privileged operation
```

Do not give the model the password.

Do not pass administrator credentials through model context.

Do not store them.

---

# 14. Privileged Helper

Install a tiny root-owned helper, for example:

```text
/usr/libexec/qwen-workspace/qwen-admin-helper
```

or distribution-appropriate equivalent.

Ownership:

```text
root:root
```

Qwen's user must not be able to modify it.

Requests should be structured rather than arbitrary Python `eval()` or shell strings.

Example:

```json
{
  "action": "restart_service",
  "target": "bluetooth.service",
  "reason": "Test Bluetooth configuration change"
}
```

Or:

```json
{
  "action": "install_package",
  "package": "openocd"
}
```

The helper converts the operation into a safe argv list.

Prefer:

```python
subprocess.run([
    "/usr/bin/systemctl",
    "restart",
    service
])
```

over:

```python
subprocess.run(command, shell=True)
```

Avoid privileged `shell=True`.

---

# 15. Destructive Operation Warning

For particularly dangerous actions, display a stronger dialog.

Example:

```text
⚠ DESTRUCTIVE SYSTEM OPERATION

Target:
    /dev/nvme0n1

Command:
    dd if=image.img of=/dev/nvme0n1 ...

This operation can destroy files or make the computer unbootable.

Back up anything you cannot afford to lose.

[ CANCEL ]

[ I UNDERSTAND — RUN ]
```

The human still controls the final action.

That is the product's safety promise:

> The AI may be wrong. We cannot prevent the owner of the computer from approving a destructive command. We can make sure the AI cannot silently press the button for them.

---

# 16. Mandatory Startup Warning

On first launch, show something similar to:

```text
EXPERIMENTAL AI WORKSPACE

This software gives a local AI assistant tools for interacting
with a real Linux computer.

We attempt to protect administrator-level and hardware-writing
operations behind explicit human authorization.

The assistant can make mistakes.

Back up anything you cannot afford to lose.

You are responsible for commands you explicitly approve.
```

Allow:

```text
[ ] Do not show this full message again
```

Keep a shorter warning accessible from Help/About.

---

# 17. Firefox Integration

Implement bidirectional integration.

## Terminal → Firefox

Commands such as:

```text
/web why is gcc producing this linker error?
```

should:

```text
query web provider
↓
collect search snippets/results
↓
optionally retrieve selected pages
↓
provide compact context to Qwen
↓
allow user to open sources in Firefox
```

Do not describe DuckDuckGo HTML scraping as an API.

Create a generic interface:

```python
class SearchProvider:
    async def search(query): ...
```

Initial implementation may use a lightweight DuckDuckGo method, but it should be replaceable.

Possible future providers:

```text
DuckDuckGo
Brave
Bing
local SearXNG
other APIs
```

---

# 18. Firefox → Terminal

Register:

```text
x-scheme-handler/qwen
```

Freedesktop desktop entries and XDG handlers provide the standard mechanism for registering application URI handlers on Linux. `xdg-open` itself resolves custom URL schemes through `x-scheme-handler/<scheme>`. ([Cgit][7])

Install:

```text
~/.local/share/applications/qwen-workspace.desktop
```

with a handler such as:

```text
qwen-protocol
```

A browser bookmarklet can perform:

```javascript
location.href =
    'qwen://selection?text=' +
    encodeURIComponent(window.getSelection().toString());
```

The protocol helper should **not launch another TUI** when one already exists.

Instead:

```text
Firefox
   ↓
qwen://
   ↓
qwen-protocol helper
   ↓
Unix socket
   ↓
existing workspace
```

---

# 19. Unix Socket IPC

Use:

```text
$XDG_RUNTIME_DIR/qwen-workspace.sock
```

The socket should be owned by the logged-in user and permissioned appropriately.

Suggested event structure:

```json
{
  "type": "browser_selection",
  "payload": "selected text",
  "source": "firefox"
}
```

Other types:

```text
browser_url
ask
open_file
terminal_output
context_request
```

Validate input length.

Never interpret received browser text as a shell command.

Browser content is **context**, not executable instruction.

---

# 20. Large Browser Selections

The bookmarklet approach is intentionally lightweight but has limits.

Large selections can produce enormous URI strings.

Therefore impose a sane v1 maximum, perhaps:

```text
16–32 KB
```

and provide an error such as:

```text
Selection too large for browser-link mode.
Copy the text or save it to a file instead.
```

A future Firefox extension using Native Messaging would be the proper solution for large transfers.

Do not make an extension mandatory for v1.

---

# 21. Context Provider Architecture

Do not put all context collection into one giant assistant function.

Create providers:

```text
providers/
    shell.py
    files.py
    git.py
    man.py
    web.py
    browser.py
    system.py
    usb.py
    pci.py
    hardware.py
    compiler.py
```

All providers return structured context.

For example:

```python
class ContextResult:
    source: str
    title: str
    content: str
    metadata: dict
```

Qwen should receive only the useful portion rather than unlimited raw output.

---

# 22. Slash Commands

Suggested initial command language:

```text
/ask
/web
/man
/file
/git
/system
/hw
/usb
/pci
/model
/context
/clear
/help
```

Examples:

```text
/man rsync exclude
```

```text
/git explain the current diff
```

```text
/usb why did this device stop enumerating?
```

```text
/pci inspect my GPU link state
```

```text
/hw diagnose the new serial adapter
```

---

# 23. Linux System Context

The model should understand and selectively use:

```text
/etc/os-release
uname
/proc
/sys
/dev
systemd
journalctl
udev
mounts
permissions
users/groups
processes
environment variables
network interfaces
package manager state
kernel modules
```

Useful tools include:

```text
systemctl
journalctl
ps
ss
ip
lsmod
modinfo
udevadm
lsblk
findmnt
df
free
lsof
dmesg
```

The assistant should prefer diagnosis before package reinstallations or configuration rewriting.

---

# 24. Hardware Awareness

A major differentiator of this project should be hardware-oriented Linux knowledge.

Qwen should understand:

```text
physical device
       ↓
electrical/protocol layer
       ↓
bus
       ↓
kernel driver
       ↓
device node/sysfs
       ↓
userspace software
```

---

# 25. USB Knowledge

The assistant should understand:

```text
USB topology
hubs
ports
host controllers
devices
interfaces
endpoints
descriptors
VID/PID
device classes
USB 2.x vs USB 3.x
Type-C distinction
enumeration
power
autosuspend
drivers
udev
```

Tools:

```text
lsusb
lsusb -t
lsusb -v
usb-devices
udevadm
/sys/bus/usb
journalctl
dmesg
```

The assistant should know that:

```text
physical port ≠ USB device ≠ interface ≠ endpoint
```

---

# 26. PCI / PCIe Knowledge

Train and prompt for understanding of:

```text
domain
bus
device
function
vendor ID
device ID
class
kernel driver
BAR
IRQ
MSI/MSI-X
PCIe generation
link width
link speed
IOMMU
lane allocation
```

Example address:

```text
0000:01:00.0

domain = 0000
bus    = 01
device = 00
function = 0
```

Runtime tools:

```text
lspci
lspci -nn
lspci -nnk
lspci -vv
/sys/bus/pci
```

Never train the model to assume that a GPU negotiating fewer lanes necessarily means failed hardware.

It should consider:

```text
CPU lane allocation
motherboard topology
M.2 lane sharing
BIOS settings
slot wiring
power states
device capability
```

---

# 27. Other Hardware Protocols

The model should have useful knowledge of:

```text
UART
I2C
SPI
CAN
GPIO
PWM
ADC
DAC
SATA
NVMe
SCSI
Ethernet
Wi-Fi
Bluetooth
JTAG
SWD
```

Not every subsystem needs tools in v1.

The architecture should allow providers to be added.

---

# 28. Microcontroller Support

The specialization should strongly cover:

```text
RP2040
RP2350
STM32 / ARM Cortex-M
ESP32
AVR / ATmega
SAMD21 / SAMD51
RISC-V microcontrollers
```

Toolchain knowledge:

```text
arm-none-eabi-gcc
clang
avr-gcc
riscv-none-elf-gcc
OpenOCD
GDB
picotool
dfu-util
esptool
avrdude
CMake
Ninja
PlatformIO
Zephyr
FreeRTOS
```

Qwen should understand workflows such as:

```text
source
 ↓
compiler
 ↓
linker
 ↓
ELF
 ↓
binary/hex/UF2
 ↓
bootloader/debug probe
 ↓
flash
 ↓
reset
 ↓
verify
```

---

# 29. Hardware Description Languages

The Linux/hardware LoRA should include:

```text
Verilog
SystemVerilog
VHDL
```

Secondary:

```text
Bluespec
```

Also include associated build/debug tools:

```text
iverilog
Verilator
Yosys
nextpnr
GTKWave
OpenFPGALoader
vendor constraint files
timing reports
```

Important concepts:

```text
synthesis vs simulation
combinational vs sequential logic
clock domains
reset synchronization
metastability
FSMs
blocking vs nonblocking assignment
timing constraints
setup/hold
pin constraints
resource utilization
```

---

# 30. Embedded-Linux Languages and Formats

Include significant exposure to:

```text
C
C++
assembly
Rust
Python
Bash
linker scripts
Makefiles
CMake
Kconfig
Device Tree
DTS/DTSI
systemd units
udev rules
JSON
YAML
TOML
```

---

# 31. LoRA Purpose

Do **not** spend the LoRA primarily teaching generic programming syntax.

Qwen2.5-Coder already has broad programming-language coverage. ([Qwen][3])

The LoRA should teach behavior and domain specialization.

Target identity:

```text
Linux Hardware Operator
```

The specialization should teach the model how to diagnose systems methodically.

---

# 32. Suggested LoRA Dataset Mix

Starting distribution:

```text
25% Linux administration / shell diagnosis

15% Linux hardware / kernel interfaces

10% USB / PCI / bus troubleshooting

15% embedded C/C++ / MCU development

10% Verilog / SystemVerilog / VHDL

10% Python / build tooling / automation

5% Rust / Go system tooling

5% configuration formats / systemd / udev / DTS

5% recovery and intentionally failed troubleshooting cases
```

Adjust after benchmarking.

---

# 33. LoRA Training Pattern

High-quality examples should repeatedly teach:

```text
problem
 ↓
collect evidence
 ↓
interpret evidence
 ↓
hypothesis
 ↓
test
 ↓
new evidence
 ↓
accept/reject hypothesis
 ↓
minimal fix
 ↓
verify
```

Include examples where the first hypothesis is wrong.

That is extremely important.

A useful operator needs to learn how to **change its mind when measurements disagree with the diagnosis**.

---

# 34. Train Concepts, Retrieve Identifiers

Do not attempt to memorize every:

```text
PCI vendor/device ID
USB VID/PID
kernel version
package version
firmware revision
```

Those facts change.

Instead:

```text
LoRA:
    understand what IDs mean
    understand how to diagnose them

Runtime:
    pci.ids
    usb.ids
    sysfs
    installed kernel
    local documentation
    web lookup
```

The machine itself is the authority for machine state.

---

# 35. LoRA Tooling

PEFT LoRA is appropriate because the original model weights remain frozen while relatively small adapter matrices are trained. PEFT also allows adapters to be merged into the base model later if desired. ([Hugging Face][8])

Train separately from the target deployment machines if necessary.

Deployment options:

```text
A. Load base + adapter dynamically.
B. Merge adapter into model.
C. Maintain several adapters and select them.
```

Prefer A initially.

That makes A/B testing much easier:

```text
stock Qwen
vs
Linux-operator LoRA
```

---

# 36. Benchmark Before and After LoRA

Create a hidden evaluation suite of at least 100 problems.

Suggested distribution:

```text
20 Linux shell/filesystem
15 systemd/services
10 networking
10 permissions
10 package/build failures
10 USB/PCI/hardware
10 embedded/MCU
10 HDL/FPGA
5 recovery/destructive-operation judgment
```

Score:

```text
correct diagnosis
useful inspection commands
unnecessary commands
dangerous commands proposed
root cause found
fix correctness
verification performed
tokens used
time to solution
```

Do not evaluate purely by whether the answer sounds knowledgeable.

---

# 37. Command Cards

When Qwen generates executable code, detect command blocks and render them specially.

Example:

```text
Qwen suggests:

┌─────────────────────────────────────────┐
│ journalctl -b -u bluetooth --no-pager  │
└─────────────────────────────────────────┘

[ COPY ]  [ RUN ]  [ EXPLAIN ]
```

For privileged commands:

```text
[ REQUEST ADMIN PERMISSION ]
```

instead of:

```text
[ RUN ]
```

---

# 38. Diff-First Editing

For source code changes, prefer:

```text
proposal
 ↓
diff
 ↓
user inspection
 ↓
apply
```

Display:

```diff
- old line
+ new line
```

before rewriting important project files.

Allow autonomous edits inside an explicitly designated AI workspace if the user enables that behavior.

---

# 39. Git Integration

Provide:

```text
/git status
/git diff
/git explain
/git review
```

Useful automatic context:

```text
current branch
uncommitted files
diff statistics
recent commit
repository root
```

Never automatically run:

```text
git reset --hard
git clean -fdx
force push
```

without explicit human approval.

---

# 40. Local Documentation Provider

Linux work frequently does not need the public web.

Provide retrieval from:

```text
man
info
/usr/share/doc
--help output
compiler help
installed package documentation
```

Example:

```text
/man systemd.service restart semantics
```

This provides version-relevant information without leaving the machine.

---

# 41. Compiler Context Filtering

Do not dump a 50,000-line build log into Qwen.

Implement extractors that prioritize:

```text
first error
last error
warnings near error
compiler invocation
file/line references
linker undefined symbols
traceback tail
test failure summary
```

Preserve access to the complete log if Qwen asks for more.

This saves context and improves small-model performance.

---

# 42. Structured Session State

A 7B model should not have to remember everything from raw chat.

Keep structured state outside the model:

```json
{
  "project": "...",
  "distro": "...",
  "kernel": "...",
  "compiler": "...",
  "current_problem": "...",
  "tested_hypotheses": [],
  "confirmed_facts": [],
  "files_changed": [],
  "pending_actions": []
}
```

Inject only relevant state into the prompt.

This is one of the best ways to compensate for a smaller local model.

---

# 43. Hardware State Cache

Likewise cache relatively stable hardware information:

```text
CPU
GPU
USB controllers
PCI devices
storage
network adapters
kernel drivers
```

Refresh manually or on detected hardware change.

Do not repeatedly spend tokens rediscovering static topology.

---

# 44. Model Prompt

The system prompt should be short and operational.

Something like:

```text
You are a local Linux engineering assistant.

Prefer inspection and evidence over guessing.

Use the machine's current state as authoritative.

Do not claim a command succeeded until its output confirms success.

Distinguish suggestions from executed actions.

Prefer minimal reversible changes.

Administrator operations and hardware writes require human authorization.

After a modification, verify the result.
```

Do not turn the system prompt into a massive Linux textbook.

Put knowledge in the model, LoRA, providers, and retrieved context.

---

# 45. System Status Bar

Always expose important runtime facts:

```text
MODEL: Qwen-Coder-7B
BACKEND: Ollama
GPU: GTX 1080 Ti
VRAM: 8.7 / 11 GB
CTX: 8192
MODE: LOCAL
WEB: OFF
ADMIN: LOCKED
```

This makes the system understandable rather than magical.

---

# 46. Offline / Web Indicator

The user should always know whether outside network access is being used.

Modes:

```text
LOCAL
WEB
```

`/web` should visibly change state for that request.

Do not silently send ordinary prompts to search engines or cloud APIs.

---

# 47. Logging and Privacy

Keep logs local.

Recommended XDG paths:

```text
~/.config/qwen-workspace/
~/.local/share/qwen-workspace/
~/.cache/qwen-workspace/
$XDG_RUNTIME_DIR/qwen-workspace.sock
```

Prompt logging should be configurable.

Avoid storing administrator credentials.

Never put passwords into AI context.

Consider redacting common credential patterns when terminal output is automatically added to Qwen context.

---

# 48. Installer

`install.sh` should:

```text
detect distro
check required packages
detect Python
create virtual environment
install TUI dependencies
detect GPU
detect available VRAM
detect Ollama
offer/install inference backend
select initial model profile
benchmark candidate configuration
create XDG directories
install launcher
install qwen:// handler
optionally install privileged helper
install Polkit action
run self-test
launch application
```

System modifications should be clearly separated from per-user installation.

Most files should live under:

```text
~/.local/
```

Only the administrator helper and associated Polkit definitions should require privileged installation.

---

# 49. Suggested Repository Layout

```text
qwen-workspace/
│
├── install.sh
├── uninstall.sh
├── README.md
├── LICENSE
├── pyproject.toml
│
├── src/
│   └── qwen_workspace/
│       │
│       ├── app.py
│       ├── config.py
│       ├── hardware_detect.py
│       │
│       ├── ui/
│       │   ├── main_screen.py
│       │   ├── terminal_panel.py
│       │   ├── assistant_panel.py
│       │   ├── status_bar.py
│       │   ├── command_card.py
│       │   └── permission_dialog.py
│       │
│       ├── terminal/
│       │   ├── session.py
│       │   └── emulator.py
│       │
│       ├── inference/
│       │   ├── base.py
│       │   ├── ollama.py
│       │   └── llama_cpp.py
│       │
│       ├── providers/
│       │   ├── shell.py
│       │   ├── files.py
│       │   ├── git.py
│       │   ├── man.py
│       │   ├── system.py
│       │   ├── hardware.py
│       │   ├── usb.py
│       │   ├── pci.py
│       │   └── web.py
│       │
│       ├── security/
│       │   ├── actions.py
│       │   ├── classifier.py
│       │   └── permissions.py
│       │
│       ├── browser/
│       │   ├── protocol.py
│       │   └── socket_server.py
│       │
│       └── context/
│           ├── manager.py
│           ├── state.py
│           └── summarizer.py
│
├── admin/
│   ├── qwen-admin-helper
│   └── org.qwenworkspace.policy
│
├── desktop/
│   └── qwen-workspace.desktop
│
├── scripts/
│   └── qwen-protocol
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── security/
│   └── hardware/
│
└── training/
    ├── datasets/
    ├── eval/
    └── lora/
```

---

# 50. Important Security Tests

Automated tests should verify that the AI environment cannot silently:

```text
acquire sudo
invoke su successfully
rewrite privileged helper
rewrite Polkit policy
write raw block devices
flash firmware
write PCI configuration
modify protected system files
```

Also test obvious indirect paths.

The goal is not to create an impossible-to-defeat security appliance.

The goal is to ensure that the normal AI execution path cannot accidentally acquire administrator privileges.

---

# 51. Important Functional Tests

Verify:

```text
bash state persists
cd persists
environment variables persist
Ctrl-C works
terminal resizing works
interactive applications work
Qwen streams tokens without freezing UI
model crash does not destroy shell
shell crash does not destroy Qwen
browser selection reaches existing session
/web failure does not crash application
GPU OOM triggers useful fallback
AI command cards render correctly
permission denial returns cleanly to Qwen
```

---

# 52. Hardware Test Matrix

At minimum eventually test:

```text
GTX 1070 8 GB
GTX 1080 Ti 11 GB
modern NVIDIA GPU
CPU-only machine
NVIDIA driver absent
Ollama absent
network disconnected
USB device hotplug
serial device
multiple PCI devices
```

Do not make unsupported hardware fatal if CPU mode can work.

---

# 53. Failure Recovery

Inference failure should not take down the terminal.

Architecture:

```text
TUI
├── terminal session
├── model service
├── context providers
└── browser socket
```

Components should restart independently where possible.

If Qwen OOMs:

```text
stop generation
↓
release model/context
↓
reduce context
↓
retry once
↓
offer smaller profile
```

Never enter an endless restart loop.

---

# 54. Initial Development Phases

## Phase 1 — Core shell + Qwen

Build:

```text
Textual application
left PTY terminal
right assistant
Ollama streaming
model configuration
basic command cards
```

Nothing else matters until this works reliably.

## Phase 2 — Context

Add:

```text
terminal output selection
files
Git
manpages
system information
```

## Phase 3 — Permission boundary

Add:

```text
privileged helper
Polkit
approval dialog
admin lock indicator
```

## Phase 4 — Browser

Add:

```text
qwen:// handler
Unix socket
bookmarklet
/web provider
open-source-in-Firefox action
```

## Phase 5 — Hardware

Add:

```text
USB provider
PCI provider
hardware summary
serial detection
microcontroller tooling
```

## Phase 6 — Specialized LoRA

Only begin training after the stock model benchmark exists.

Otherwise there is no reliable way to know whether the LoRA helped.

---

# 55. Features Worth Adding After v1

High-value extensions:

```text
LSP integration
symbol search
semantic code search
patch/diff workflow
session restore
terminal command history awareness
Git checkpoint before large AI edits
serial monitor
GDB integration
OpenOCD integration
FPGA synthesis viewer
USB topology viewer
PCI topology viewer
hardware datasheet context
device-tree assistant
local documentation index
```

---

# 56. FPGA Development Mode

A future FPGA mode could expose:

```text
SYNTHESIZE
SIMULATE
TIMING
PROGRAM
```

Qwen can automatically run:

```text
iverilog
Verilator
Yosys
nextpnr
```

but:

```text
PROGRAM DEVICE
```

is a hardware-write boundary and therefore needs authorization.

Simulation does not.

---

# 57. Microcontroller Development Mode

Likewise:

```text
BUILD         → automatic
TEST          → automatic
DISASSEMBLE   → automatic
DEBUG         → automatic/read-oriented
FLASH         → permission required
ERASE         → permission required
FUSES         → permission required
EEPROM WRITE  → permission required
```

This creates a consistent mental model.

---

# 58. Backup Awareness

Do not make backup management mandatory for v1.

However, before destructive operations, remind the user:

```text
Back up anything you cannot afford to lose.
```

Later the system can optionally detect:

```text
Timeshift
Btrfs snapshots
Git cleanliness
recent project backup
```

This is useful but should not block the initial release.

---

# 59. One Important Limitation

Administrator permission alone does **not** protect files writable by the normal user.

For example:

```bash
rm -rf ~/Documents
```

does not require root.

Therefore autonomous AI command execution should occur primarily inside a designated AI/project workspace.

Commands affecting the broader user home should normally be proposed to the human terminal rather than silently executed.

This gives us a strong practical safety boundary without creating an elaborate sandboxing project.

---

# 60. Non-Goals for v1

Do not attempt to build:

```text
an entirely new Linux distribution
a new terminal emulator from scratch unless necessary
a replacement desktop environment
a fully autonomous root administrator
a browser automation framework
a massive IDE
a cloud AI service
an undefeatable security sandbox
an automatic BIOS flashing system
```

Keep the initial goal narrow.

---

# 61. Product Identity

The distinctive value is not:

> “Chatbot inside a terminal.”

It is:

> “A local Linux engineering assistant attached to a real operating environment.”

Eventually:

```text
Linux
 ↓
kernel
 ↓
hardware buses
 ↓
embedded systems
 ↓
FPGA
 ↓
microcontrollers
```

all become understandable through the same interface.

---

# 62. UX Philosophy

The machine should never make the user wonder:

```text
Did the AI actually run that?
```

Use explicit visual states:

```text
SUGGESTED
RUNNING
COMPLETED
FAILED
ADMIN APPROVAL REQUIRED
DENIED
```

After running something, Qwen should receive the real exit code and output.

Example:

```text
COMMAND
make

EXIT
2

STDERR
undefined reference to `usb_init'
```

The model should reason from that evidence.

---

# 63. Suggested Internal Action Structure

Represent commands internally rather than passing random text everywhere.

Example:

```json
{
  "id": "cmd-173",
  "argv": [
    "/usr/bin/systemctl",
    "restart",
    "bluetooth.service"
  ],
  "cwd": "/home/user/project",
  "source": "assistant",
  "privileged": true,
  "hardware_write": false,
  "reason": "Restart service after configuration change"
}
```

This also makes logging and approval much cleaner.

---

# 64. Avoid Shell Injection Internally

Whenever application code launches commands, prefer argv arrays:

```python
await asyncio.create_subprocess_exec(
    "/usr/bin/lspci",
    "-nnk"
)
```

rather than:

```python
await asyncio.create_subprocess_shell(
    f"lspci {user_input}"
)
```

The user's interactive terminal can obviously remain a normal shell.

The application's internal service calls should not unnecessarily invoke one.

---

# 65. AI Tool Interface

Eventually give Qwen structured tools such as:

```text
read_file(path)
list_directory(path)
run_workspace_command(argv)
get_git_diff()
query_manpage(topic)
inspect_usb()
inspect_pci()
inspect_system()
search_web(query)
request_admin_action(action)
```

This is preferable to telling the model:

> “Just type whatever commands you want into Bash.”

It also makes the LoRA's behavior easier to train and evaluate.

---

# 66. Hardware Write Rule

Hard rule:

```text
READ:
generally okay

WRITE:
user approval
```

Especially:

```text
firmware
EEPROM
flash
fuses
raw block device
PCI config
MMIO
bootloader
partition table
```

This rule should be enforced by application architecture, not merely by the model prompt.

---

# 67. Browser Security Rule

Anything coming from a webpage is untrusted text.

The browser bridge must never transform:

```text
website content
```

directly into:

```text
executed command
```

Correct flow:

```text
browser text
 ↓
AI context
 ↓
AI analysis
 ↓
command proposal
 ↓
human/run policy
```

---

# 68. Practical Model Strategy

Do not spend months optimizing the perfect model before the workstation exists.

Build around stock Qwen first.

Sequence:

```text
stock Qwen
 ↓
benchmark
 ↓
build useful tools
 ↓
benchmark again
 ↓
create Linux/hardware training corpus
 ↓
LoRA
 ↓
compare against original
```

Tools may improve performance more dramatically than training.

---

# 69. Why Tools Matter So Much

A 7B model does not need to memorize:

```text
current kernel
current package version
current PCI topology
current compiler error
current systemd state
```

Linux can answer those questions.

The architecture should therefore maximize:

```text
good reasoning
+
good measurements
```

rather than attempting to make the model omniscient.

---

# 70. First Release Acceptance Criteria

Version 0.1 is successful when all of the following work reliably:

```text
Application installs on Linux Mint.

A real persistent Bash terminal works in the left panel.

Qwen runs locally and streams responses in the right panel.

GTX 1070/1080-Ti-class hardware gets sensible automatic defaults.

The user can send terminal output to Qwen.

Qwen can propose commands.

The user can send commands to the terminal.

Qwen can inspect Linux system information.

Qwen can inspect USB and PCI information.

A qwen:// Firefox link reaches the active application.

Basic /web research works.

Privileged actions require explicit approval.

Qwen never receives persistent administrator privileges.

Hardware-writing actions require explicit approval.

Denial leaves the system in a clean state.

AI/model failure does not destroy the user's terminal session.
```

Anything beyond those requirements is secondary.

---

# 71. Development Priority

Optimize in this order:

```text
1. Reliability
2. Safety boundary
3. Terminal usability
4. Model usefulness
5. Hardware awareness
6. Speed
7. Appearance
```

A gorgeous terminal that occasionally corrupts state is a failure.

A plain terminal that reliably diagnoses the machine is useful.

---

# 72. Final Architecture

```text
                    ┌─────────────────────────┐
                    │      install.sh         │
                    │                         │
                    │ hardware detection      │
                    │ model selection         │
                    │ XDG integration         │
                    │ optional admin helper   │
                    └───────────┬─────────────┘
                                │
                                ▼
┌───────────────────────────────────────────────────────────────┐
│                     TEXTUAL WORKSPACE                         │
│                                                               │
│  ┌────────────────────────┐   ┌────────────────────────────┐  │
│  │     HUMAN TERMINAL     │   │       QWEN ASSISTANT       │  │
│  │                        │   │                            │  │
│  │  persistent PTY        │   │ local inference           │  │
│  │  interactive Bash      │   │ Linux reasoning           │  │
│  │  real terminal state   │   │ hardware reasoning        │  │
│  └────────────┬───────────┘   └──────────────┬─────────────┘  │
│               │                              │                │
│               │        CONTEXT BUS           │                │
│               └──────────────┬───────────────┘                │
│                              │                                │
│          ┌───────────────────┼────────────────────┐           │
│          ▼                   ▼                    ▼           │
│        files               system              hardware       │
│        git                 manpages            USB            │
│        build               logs                PCI            │
│          │                   │                    │           │
│          └───────────────────┼────────────────────┘           │
│                              │                                │
│                              ▼                                │
│                      ACTION MANAGER                           │
│                         │        │                            │
│                    normal     privileged                      │
│                         │        │                            │
│                         ▼        ▼                            │
│                    AI workspace  PERMISSION BUTTON            │
│                                      │                        │
└──────────────────────────────────────┼────────────────────────┘
                                       │
                                       ▼
                               ┌──────────────┐
                               │    POLKIT    │
                               │ admin helper │
                               └──────┬───────┘
                                      │
                                      ▼
                                  Linux OS


Firefox
   │
   ├── qwen:// selected text
   │
   ▼
Unix socket ─────────────────────────────► context bus

Qwen
   │
   └── /web ─────────────────────────────► search provider
```

---

# 73. Core Product Rule

Keep this line visible in the source documentation because it summarizes the security design:

```text
Qwen may recommend the dangerous action.

Qwen may explain the dangerous action.

Qwen may prepare the dangerous action.

Qwen does not get to approve the dangerous action.
```

The user owns the computer.

The user owns the button.

---

[1]: https://textual.textualize.io/guide/workers/ "Workers - Textual"
[2]: https://github.com/mitosch/textual-terminal "textual-terminal"
[3]: https://qwenlm.github.io/blog/qwen2.5-coder/ "Qwen2.5-Coder"
[4]: https://github.com/ggml-org/llama.cpp/blob/master/src/llama-adapter.cpp "llama.cpp adapters"
[5]: https://github.com/ollama/ollama/blob/main/envconfig/config.go "Ollama envconfig"
[6]: https://polkit.pages.freedesktop.org/polkit/polkit.8.html "polkit reference manual"
[7]: https://cgit.freedesktop.org/xdg/xdg-utils/tree/scripts/xdg-open.in "xdg-open"
[8]: https://huggingface.co/docs/peft/en/package_reference/lora "PEFT LoRA"
