# Exposure watch: what the internet can reach, against what is declared

A scanner host checks every public address of the fleet daily and alerts on anything open that is not declared. Two independent views:
an **active scan** (nmap, all TCP ports, low rate; authoritative and immediate) and **Shodan** (the API with your key, or the free InternetDB; shows what
the internet has already indexed and any known vulnerabilities, but lags by days).

## Declared ports

`config/vars/group/util_exposure.yml`, `exposure_watch_targets`: for each target its public addresses (IPv4 and IPv6) and the ports it is supposed to
expose (`tcp`, optionally `udp`). The web hosts declare 80 and 443; a tailnet-only host such as a backup target declares nothing. Get a host's
public address with `scripts/fleet-run.sh <host> -- 'curl -4 -s https://api.ipify.org'`. A host skips targets named like itself, so the scanner is
not scanned from itself: give a second host `util: [exposure]` to cover it.

## First run

1. `scripts/exposure.sh init` (asks for the Shodan key, hidden; Enter for none), review, commit, push, `scripts/reconcile-now.sh <host>`.
2. `scripts/exposure.sh learn` prints what is open now as YAML. **Review it before declaring it**: anything there you did not intend is a finding, not a baseline.
3. Put the intended ports in `util_exposure.yml`; `scripts/exposure.sh check` shows the findings against them.

## What it reports

| Finding | Meaning |
|---|---|
| `unexpected-open` (alert) | a port is open that is not declared |
| `shodan-vuln` (alert) | Shodan lists a known vulnerability for the address |
| `expected-closed` (warn) | a declared port did not answer (a service is down, or the firewall changed) |
| `shodan-only` (info) | Shodan lists a port the scan did not see (closed since, or filtered from this vantage) |

New alerts and warnings are sent once to Pushover (through `fleet-notify`), repeated weekly while they persist, and a note is sent when they clear. Every scan and
finding is also a JSON line in the journal, so it reaches Loki and the cmdr page.

## Notes

- Docker-published ports bypass `ufw`; the Docker guard closes them, and this watch is the outside check that proves it.
- Keep the scan rate low (`exposure_watch_max_rate`, 300 packets per second by default) and scan only addresses you own; some providers ask to be told about regular scans.
- The scanner's own address is covered by Shodan only until another host scans it.
