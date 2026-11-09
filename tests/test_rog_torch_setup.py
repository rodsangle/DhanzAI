import json
import runpy
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
setup = runpy.run_path(str(ROOT / 'apps/rog_video_worker/setup_torch_wsl.py'))
probe = {'__name__': 'isolated_probe_tests'}
exec(compile(setup['GPU_PROBE'], '<gpu_probe>', 'exec'), probe)  # noqa: S102 - reviewed embedded source


class RogTorchSetupTests(unittest.TestCase):
    def test_only_matching_rocm_and_gpu_are_accepted(self):
        check = probe['validate_backend']
        check('2.11.0+rocm7.2', '7.2.123', True, 'gfx1151:sramecc-:xnack-')
        for values in [('2.11.0+cpu', None, False, ''),
                       ('2.11.0+rocm7.2', '7.2.123', False, ''),
                       ('2.11.0+rocm7.2', '7.2.123', True, 'gfx1100')]:
            with self.subTest(values=values), self.assertRaises(RuntimeError):
                check(*values)

    def test_failed_probe_removes_stale_success(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            marker = state / 'pytorch-check.json'
            marker.write_text('{"old_success":true}')
            def failure():
                raise RuntimeError('Synthetic GPU failure')
            with self.assertRaises(RuntimeError):
                probe['check'](state, failure)
            self.assertFalse(marker.exists())

    def test_success_marker_is_private_and_created_only_after_probe(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            result = probe['check'](state, lambda: {'checks': ['synthetic test only']})
            marker = state / 'pytorch-check.json'
            self.assertIn('checked_at', result)
            self.assertEqual(json.loads(marker.read_text())['checks'], ['synthetic test only'])
            self.assertEqual(marker.stat().st_mode & 0o777, 0o600)

    def test_official_wheel_and_hash_are_pinned(self):
        self.assertTrue(setup['TORCH_WHEEL'].startswith('https://download-r2.pytorch.org/whl/rocm7.2/torch-2.11.0'))
        self.assertIn('cp312-cp312-manylinux_2_28_x86_64.whl#sha256=', setup['TORCH_WHEEL'])


if __name__ == '__main__':
    unittest.main()
