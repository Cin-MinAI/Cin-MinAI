#!/usr/bin/env bash
# Hands-on test on the Mint desktop: a *separate* Firefox (throwaway profile) with the signed
# extension, the native messaging host registered for this user, and a test page.
#   ./live.sh [URL]      start          ./live.sh stop     close it and remove everything it added
# The host registration only answers to our extension's id (assistant@cinminai.org), so the
# user's normal Firefox profile is unaffected.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
profile=/tmp/cinminai-ff-profile
nmh=~/.mozilla/native-messaging-hosts/org.cinminai.assistant.json
export DISPLAY=${DISPLAY:-:0} DBUS_SESSION_BUS_ADDRESS=${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/$(id -u)/bus}

if [[ ${1:-} == stop ]]; then
    pkill -f -- "-profile $profile" || true
    sleep 2
    rm -rf "$profile" "$nmh"
    echo "stopped and cleaned up"
    exit 0
fi

xpi=$(ls "$here"/dist/cinminai_assistant-*.xpi | tail -1)
mkdir -p "$(dirname "$nmh")" "$profile/extensions"
sed "s|@HOST_PATH@|$here/host/cinminai-firefox-host|" "$here/host/org.cinminai.assistant.json.in" > "$nmh"
cp "$xpi" "$profile/extensions/assistant@cinminai.org.xpi"
cat > "$profile/user.js" <<'EOF'
// Throwaway test profile: enable the sideloaded extension without the "add extension?" prompt.
user_pref("extensions.autoDisableScopes", 0);
user_pref("extensions.enabledScopes", 15);
user_pref("browser.shell.checkDefaultBrowser", false);
user_pref("browser.aboutwelcome.enabled", false);
user_pref("datareporting.policy.dataSubmissionEnabled", false);
EOF
url=${1:-https://en.wikipedia.org/wiki/Raspberry_Pi}
setsid firefox --no-remote -profile "$profile" "$url" >/dev/null 2>&1 < /dev/null &
echo "Firefox (test profile) opening $url"
