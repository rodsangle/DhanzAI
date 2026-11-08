#!/usr/bin/env bash
# Ubuntu 24.04 / WSL2 GPU runtime setup. No models, API keys, or AWS changes.
set -Eeuo pipefail

ROCM_VERSION=7.2.4
BRIDGE_URL=https://github.com/ROCm/librocdxg/releases/download/v1.2.1/rocdxg-roct_1.2.1_amd64.deb
BRIDGE_SHA256=7889eef45a1132ed2dde88d8ea1356bf791ec9c05802a18940bc81b970e850e0
REPOSITORY='deb [arch=amd64 signed-by=/etc/apt/keyrings/dhanz-rocm.gpg] https://repo.radeon.com/rocm/apt/7.2.4 noble main'

fail() { printf '%s\n' "$*" >&2; exit 1; }

runtime_candidate() {
    # Consume every line: an early awk exit can SIGPIPE apt-cache under pipefail.
    apt-cache policy rocm-hip-runtime | awk '/Candidate:/ && !found { print $2; found=1 }'
}

required_rocminfo_version() {
    # Read the full control record before parsing, so pipefail cannot hide SIGPIPE.
    apt-cache show "rocm-hip-runtime=$1" | python3 -c '
import re, sys
metadata = sys.stdin.read()
match = re.search(r"\brocminfo\s*\(=\s*([^)]+)\)", metadata)
if match is None:
    raise SystemExit("The ROCm runtime metadata has no exact rocminfo dependency. Installation stopped.")
version = match.group(1).strip()
if not re.fullmatch(r"[0-9A-Za-z.+:~_-]+", version):
    raise SystemExit("The rocminfo dependency version is invalid. Installation stopped.")
print(version)
'
}

main() {
    local apply=false
    case "${1:-}" in
        --apply) apply=true ;;
        --help|-h) printf '%s\n' 'Usage: bash setup_amd_wsl.sh [--apply]' 'Without --apply, prints the plan only.'; return ;;
        '') ;;
        *) fail 'Unknown argument. Use --apply to install or --help for usage.' ;;
    esac
    [[ $# -le 1 ]] || fail 'Pass only --apply or --help.'
    [[ $(id -u) -ne 0 ]] || fail 'Run as your Ubuntu user, not root. The installer uses sudo for packages.'
    [[ $(uname -m) == x86_64 ]] || fail 'This installer requires x86_64.'
    grep -qi microsoft /proc/sys/kernel/osrelease || fail 'Run this inside Ubuntu-24.04 on WSL2.'
    # The file is supplied by the installed distribution, not by a downloaded script.
    source /etc/os-release
    [[ ${ID:-} == ubuntu && ${VERSION_ID:-} == 24.04 ]] || fail 'Select Ubuntu-24.04; other distributions were not changed.'
    [[ -r /dev/dxg && -w /dev/dxg ]] || fail 'WSL GPU access is unavailable. Check Windows AMD drivers and WSL before installing.'
    [[ -f /usr/lib/wsl/lib/libdxcore.so ]] || fail 'Microsoft DXCore is missing in WSL. Update WSL/Windows GPU support first.'
    printf '%s\n' "Plan: ROCm $ROCM_VERSION user-space runtime and ROCDXG 1.2.1, then test gfx1151."
    if [[ $apply != true ]]; then
        printf '%s\n' 'Nothing installed. Rerun with --apply to install this runtime.'
        return
    fi

    local state_dir="$HOME/.local/share/dhanz-rog"
    local sources=/etc/apt/sources.list.d/dhanz-rocm.list
    local keyring=/etc/apt/keyrings/dhanz-rocm.gpg
    local preferences=/etc/apt/preferences.d/dhanz-rocm
    local bridge="$state_dir/rocdxg-roct_1.2.1_amd64.deb"
    local plan="$state_dir/runtime-package-plan.txt"
    local log="$state_dir/rocminfo.txt"
    mkdir -p "$state_dir"
    chmod 700 "$state_dir"
    # Keep an existing unrelated ROCm installation intact.
    local item
    for item in /etc/apt/sources.list /etc/apt/sources.list.d/*.list /etc/apt/sources.list.d/*.sources; do
        [[ -f $item && $item != "$sources" ]] || continue
        if grep -Eq '^[^#]*(repo\.radeon\.com/rocm|repo\.amd\.com/rocm)' "$item"; then
            fail 'An existing ROCm repository is configured. Stop here and share this message before changing it.'
        fi
    done
    if [[ -f $sources ]] && [[ $(cat "$sources") != "$REPOSITORY" ]]; then
        fail 'The Dhanz ROCm repository entry differs. No existing repository was overwritten.'
    fi

    sudo -v
    sudo apt-get update
    sudo apt-get install -y --no-install-recommends ca-certificates curl gnupg python3-venv python3-pip ffmpeg
    curl --proto '=https' --proto-redir '=https' --tlsv1.2 -fL \
        https://repo.radeon.com/rocm/rocm.gpg.key -o "$state_dir/amd-release.asc"
    gpg --batch --yes --dearmor --output "$state_dir/amd-release.gpg" "$state_dir/amd-release.asc"
    sudo install -d -m 0755 /etc/apt/keyrings
    sudo install -m 0644 "$state_dir/amd-release.gpg" "$keyring"
    printf '%s\n' "$REPOSITORY" > "$state_dir/dhanz-rocm.list"
    sudo install -m 0644 "$state_dir/dhanz-rocm.list" "$sources"
    # AMD's packages must outrank Ubuntu builds of tools such as rocminfo.
    printf '%s\n' 'Package: *' 'Pin: origin "repo.radeon.com"' 'Pin-Priority: 600' > "$state_dir/dhanz-rocm.preferences"
    if [[ -f $preferences ]] && ! cmp -s "$preferences" "$state_dir/dhanz-rocm.preferences"; then
        fail 'The Dhanz ROCm package preference differs. No existing preference was overwritten.'
    fi
    sudo install -m 0644 "$state_dir/dhanz-rocm.preferences" "$preferences"
    sudo apt-get update
    local candidate rocminfo_version
    printf '%s\n' 'Checking available ROCm runtime version...'
    candidate=$(runtime_candidate)
    printf 'ROCm candidate: %s\n' "${candidate:-none}"
    [[ $candidate == 7.2.4* ]] || fail "ROCm 7.2.4 packages are unavailable for this setup. Nothing else will be installed."
    rocminfo_version=$(required_rocminfo_version "$candidate")
    printf 'Matching rocminfo: %s\n' "$rocminfo_version"
    curl --proto '=https' --proto-redir '=https' --tlsv1.2 -fL "$BRIDGE_URL" -o "$bridge"
    printf '%s  %s\n' "$BRIDGE_SHA256" "$bridge" | sha256sum --check --status || fail 'AMD WSL bridge checksum mismatch. Installation stopped.'
    if ! sudo apt-get --simulate --no-install-recommends install "rocm-hip-runtime=$candidate" "rocminfo=$rocminfo_version" "$bridge" > "$plan" 2>&1; then
        tail -n 80 "$plan"
        fail 'The GPU package dependency check failed. No GPU packages were installed; share the dependency details above.'
    fi
    if grep -Ei '^Inst .*([Dd][Kk][Mm][Ss]|linux-image|linux-headers)' "$plan"; then
        fail 'The package plan includes a Linux kernel/driver package. Stopped before installing that plan.'
    fi
    sudo apt-get install -y --no-install-recommends "rocm-hip-runtime=$candidate" "rocminfo=$rocminfo_version" "$bridge"
    [[ -x /opt/rocm/bin/rocminfo ]] || fail 'rocminfo was not found in /opt/rocm/bin. Share the final installation lines.'

    cat > "$state_dir/amd-env.sh" <<'ENV'
# Required for the ROCm 7.2 WSL bridge. Source this before GPU programs.
export HSA_ENABLE_DXG_DETECTION=1
export PATH="/opt/rocm/bin:$PATH"
export LD_LIBRARY_PATH="/usr/lib/wsl/lib:/opt/rocm/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
ENV
    chmod 600 "$state_dir/amd-env.sh"
    source "$state_dir/amd-env.sh"
    if ! timeout 60 /opt/rocm/bin/rocminfo > "$log" 2>&1; then
        printf '%s\n' 'GPU test did not pass. AMD runtime installed; no model was downloaded.'
        tail -n 60 "$log"
        return 1
    fi
    if ! grep -Eq 'Name:[[:space:]]+gfx1151([[:space:]]|$)' "$log"; then
        printf '%s\n' 'ROCm ran, but gfx1151 was not detected. No model was downloaded.'
        grep -E 'Name:|Marketing Name:|Device Type:' "$log" || true
        return 1
    fi
    printf '%s\n' 'AMD GPU CHECK: PASS (gfx1151 / Radeon 8060S)' \
        'ROCm runtime and WSL bridge installed. PyTorch and Wan still need setup.' \
        "GPU environment file: $state_dir/amd-env.sh" \
        'AWS configuration is unchanged. No video generation or provider charge was started.'
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
    trap 'dhanz_failure_status=$?; printf "AMD setup stopped at line %s (exit %s).\n" "$LINENO" "$dhanz_failure_status" >&2; exit "$dhanz_failure_status"' ERR
    main "$@"
fi
