# Cin-minAI shell integration for bash (M0 spike). Used as --rcfile by relay.py.
#
# Emits OSC 133 semantic prompt markers and OSC 7 (cwd) for the relay:
#   A = prompt start, B = prompt end / input start, C = command output start, D;<exit> = command end
# plus a private OSC 7717 for the command text and the sharing switch (`ai on|off`).
# Terminals ignore OSCs they don't know, so everything is safe to pass through unchanged.

# The user's normal startup first. (Debian/Ubuntu bash reads /etc/bash.bashrc itself, even
# with --rcfile.)
[ -f ~/.bashrc ] && . ~/.bashrc

__cmai_on=1
__cmai_ind='◆ '

__cmai_precmd() {
    local ec=$?
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
        on)  __cmai_on=1; __cmai_ind='◆ '; printf '\e]7717;ai=on\a' ;;
        *)   if [[ $__cmai_on == 1 ]]; then echo "ai: this terminal is shared with the assistant (ai off to stop)"
             else echo "ai: this terminal is private (ai on to share)"; fi ;;
    esac
}

PS0='$(__cmai_preexec)'
PS1='\[\e]133;A\a\]${__cmai_ind}'"$PS1"'\[\e]133;B\a\]'
PROMPT_COMMAND=(__cmai_precmd "${PROMPT_COMMAND[@]}")
