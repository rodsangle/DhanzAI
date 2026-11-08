"""Validate the runtime installer without installing packages or pretending to have a GPU."""
import hashlib
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'apps/rog_video_worker/setup_amd_wsl.sh'


class RogRuntimeSetupTests(unittest.TestCase):
    def test_shell_syntax_and_help_have_no_installation(self):
        result = subprocess.run(['bash', '-n', str(SCRIPT)], capture_output=True, text=True, check=False)  # noqa: S603 - fixed checker
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run(['bash', str(SCRIPT), '--help'], capture_output=True, text=True, check=False)  # noqa: S603 - fixed helper
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('plan only', result.stdout)

    def test_installer_stops_on_wrong_machine_before_sudo(self):
        code = 'source "$1"; id() { printf "1000"; }; uname() { printf "x86_64"; }; grep() { return 1; }; main'
        result = subprocess.run(  # noqa: S603 - constant guard test, no package commands are reached
            ['bash', '-c', code, '_', str(SCRIPT)], capture_output=True, text=True, check=False
        )
        # Simulate a non-WSL host before any package operations, on any real test host.
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('WSL2', result.stderr)
        self.assertNotIn('sudo:', result.stderr)

    def test_version_check_drains_package_output_with_pipefail(self):
        code = r'''source "$1"
apt-cache() {
    printf 'rocm-hip-runtime:\n  Installed: (none)\n  Candidate: 7.2.4.70204-93~24.04\n'
    for ((i=0; i<20000; i++)); do printf 'remaining package policy information %s\n' "$i"; done
}
candidate=$(runtime_candidate)
[[ $candidate == '7.2.4.70204-93~24.04' ]]
'''
        result = subprocess.run(  # noqa: S603 - fixed synthetic package-output regression, no sudo or network
            ['bash', '-c', code, '_', str(SCRIPT)], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_matching_rocminfo_is_taken_from_runtime_dependency(self):
        code = r'''source "$1"
apt-cache() {
    [[ $1 == show && $2 == 'rocm-hip-runtime=7.2.4.70204-93~24.04' ]] || return 2
    printf 'Package: rocm-hip-runtime\nVersion: 7.2.4.70204-93~24.04\nDepends: rocm-core,\n rocminfo (= 1.0.0.70204-93~24.04), hip-runtime-amd\n'
}
version=$(required_rocminfo_version '7.2.4.70204-93~24.04')
[[ $version == '1.0.0.70204-93~24.04' ]]
'''
        result = subprocess.run(  # noqa: S603 - synthetic APT metadata, no sudo or network
            ['bash', '-c', code, '_', str(SCRIPT)], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unknown_dependency_metadata_stops_installation(self):
        code = r'''source "$1"
apt-cache() { printf 'Package: rocm-hip-runtime\nDepends: rocm-core\n'; }
required_rocminfo_version '7.2.4'
'''
        result = subprocess.run(  # noqa: S603 - synthetic APT metadata guard
            ['bash', '-c', code, '_', str(SCRIPT)], capture_output=True, text=True, check=False
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('no exact rocminfo dependency', result.stderr)

    def test_official_bridge_checksum_is_pinned(self):
        text = SCRIPT.read_text()
        self.assertIn('7889eef45a1132ed2dde88d8ea1356bf791ec9c05802a18940bc81b970e850e0', text)
        artifact = Path('/tmp/rocdxg-roct_1.2.1_amd64.deb')
        if artifact.is_file():
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            self.assertIn('BRIDGE_SHA256=' + digest, text)


if __name__ == '__main__':
    unittest.main()
