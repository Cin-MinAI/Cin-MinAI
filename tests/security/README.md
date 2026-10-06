# Security checks

Run the user-level suite from the repository root:

```sh
PYTHONPATH=src python3 tests/security/check_security.py
```

`check_security.py` runs the real bubblewrap sandbox probes from `tests/sandbox/check_sandbox.py`, then the
admin-policy and browser-boundary negative tests. A release/test install must have `pasta` (the `passt` package):
the production sandbox uses its private network, and falls back to no network if it is unavailable. `host` is an
explicit test-only mode and is expected to expose host loopback and abstract X sockets.

## Installed-mechanism test on the disposable test SSD

Do not run this part on a personal/live install. Install the locally built `cinminai-admin` package on the test
SSD, then use `admin_call.py`. Calls without `--interactive` must fail without opening an authentication dialog.
Valid calls with `--interactive` must show a fresh administrator-password dialog every time, including two
identical calls in succession. Cancel at least one dialog and verify that it is recorded as a denial.

Safe rejection probes (none may show polkit):

```sh
python3 tests/security/admin_call.py restart dbus.service
python3 tests/security/admin_call.py remove sudo
python3 tests/security/admin_call.py write /etc/sudoers x
python3 tests/security/admin_call.py write /etc/cinminai-missing-parent/x.conf x
python3 tests/security/admin_call.py unload nvme
python3 tests/security/admin_call.py run /usr/sbin/wipefs --all '/dev/sd*'
python3 tests/security/admin_call.py run /usr/sbin/wipefs --all "$(findmnt -nro SOURCE / | sed 's/[0-9]*$//')"
```

For positive tests, use only disposable fixtures: a harmless test service, a throwaway package, a test file under
`/etc`, the `dummy` kernel module, and an unmounted loop device backed by a temporary file. Record the state before
each call and restore it afterward. Never pass an installed disk to `RunArgv`.

After the eight verbs, one denial, and the rejection probes, inspect `/var/log/cinminai/admin.log`. Every accepted
request must have `request`, `authorization-requested`, `authorization-approved`, and `result` events with one
request id. A cancelled request has `authorization-denied`; a pre-polkit refusal has `request` and `rejected` only.
Each row's `prev` must equal the preceding row's `hash`.
