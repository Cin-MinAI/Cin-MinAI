# SPDX-License-Identifier: GPL-3.0-or-later
# Cin-MinAI terminal sharing (D77): sourced from the person's ~/.bashrc, a line added only after they said yes
# (cin_minai.shell.ctl.enable). Starts this terminal's shell through the relay, so the assistant can see its
# commands and their output — with the ◆ marker in the prompt, and `ai off` to stop.
#
# Only for an interactive shell on a terminal, once (the relay's own shell has CINMINAI_RELAY), and not under
# sudo/su (root keeps its own startup), ssh (remote logins) or a terminal multiplexer (spike finding 3: an
# environment variable alone doesn't survive `sudo -i`).
if [[ $- == *i* && -t 0 && -t 1 && -z ${CINMINAI_RELAY:-} && -z ${SSH_CONNECTION:-} && -x /usr/bin/cinminai-relay ]]; then
    case $(cat /proc/$PPID/comm 2>/dev/null) in
        sudo|su|sshd|sshd-session|tmux*|screen|script) ;;
        *) exec /usr/bin/cinminai-relay ;;
    esac
fi
