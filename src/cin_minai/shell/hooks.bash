# SPDX-License-Identifier: GPL-3.0-or-later
# Cin-MinAI shell integration for bash (M3, SPEC §6.2). The relay starts bash with this file as --rcfile.
#
# Emits OSC 133 semantic prompt markers and OSC 7 (cwd) for the relay:
#   A = prompt start, B = prompt end / input start, C = command output start, D;<exit> = command end
# plus a private OSC 7717 for the command text and the sharing switch (`ai on|off`).
# Terminals ignore OSCs they don't know, so everything is safe to pass through unchanged.

# The user's normal startup first. (Debian/Ubuntu bash reads /etc/bash.bashrc itself, even with --rcfile.) Their
# ~/.bashrc sources start.bash, which sees CINMINAI_RELAY and does nothing this time.
[ -f ~/.bashrc ] && . ~/.bashrc

__cmai_on=1
__cmai_ind=''

__cmai_precmd() {
    local ec=$?
    # The ◆ marker shows only while something is listening: sharing on and the relay's analyzer alive (its socket
    # exists). If the analyzer couldn't start or died, the terminal works as before, without the marker.
    if [[ $__cmai_on == 1 && -S ${CINMINAI_SOCK:-/nonexistent} ]]; then __cmai_ind='◆ '; else __cmai_ind=''; fi
    # History number of the last entry, so preexec can tell whether the next command
    # was recorded (HISTCONTROL=ignorespace hides " cmd": then we don't report its text).
    local h
    h=$(HISTTIMEFORMAT= builtin history 1)
    h=${h#"${h%%[! ]*}"}
    __cmai_hnum=${h%%[!0-9]*}
    printf '\e]133;D;%s\a\e]7;file://%s%s\a' "$ec" "$HOSTNAME" "$PWD"
}

# Runs from PS0 (after a command line is read, before it runs), in a subshell.
__cmai_preexec() {
    local h num cmd
    h=$(HISTTIMEFORMAT= builtin history 1)
    h=${h#"${h%%[! ]*}"}
    num=${h%%[!0-9]*}
    if [[ $__cmai_on == 1 && -n $num && $num != "$__cmai_hnum" ]]; then
        cmd=${h#"$num"}
        cmd=${cmd#"  "}
        cmd=${cmd//%/%25}
        cmd=${cmd//$'\n'/%0A}
        cmd=${cmd//$'\r'/%0D}
        cmd=${cmd//$'\a'/%07}
        cmd=${cmd//$'\e'/%1B}
        printf '\e]7717;cmd=%s\a' "$cmd"
    elif [[ $__cmai_on == 1 ]]; then
        # Not added to history: a repeat (ignoredups) or hidden (ignorespace, history off).
        # The relay decides from the screen.
        printf '\e]7717;unrecorded\a'
    fi
    printf '\e]133;C\a'
}

ai() {
    case $1 in
        off) __cmai_on=0; __cmai_ind=''; printf '\e]7717;ai=off\a' ;;
        on)  __cmai_on=1; printf '\e]7717;ai=on\a' ;;
        *)   if [[ $__cmai_on == 1 && -S ${CINMINAI_SOCK:-/nonexistent} ]]; then
                 echo "ai: this terminal is shared with the assistant (ai off to stop)"
             elif [[ $__cmai_on == 1 ]]; then
                 echo "ai: sharing is on, but nothing is listening in this terminal: the assistant sees nothing"
             else echo "ai: this terminal is private (ai on to share)"; fi ;;
    esac
}

PS0='$(__cmai_preexec)'
PS1='\[\e]133;A\a\]${__cmai_ind}'"$PS1"'\[\e]133;B\a\]'
PROMPT_COMMAND=(__cmai_precmd "${PROMPT_COMMAND[@]}")
