import contextlib
import hashlib
import io
import json
import runpy
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
module = runpy.run_path(str(ROOT / 'apps/rog_video_worker/setup_wan_preview.py'))


class WanPreviewTests(unittest.TestCase):
    def test_only_data_files_are_selected_for_download(self):
        info = SimpleNamespace(siblings=[
            SimpleNamespace(rfilename='transformer/model.safetensors', size=123),
            SimpleNamespace(rfilename='tokenizer/spiece.model', size=20),
            SimpleNamespace(rfilename='model_index.json', size=30),
            SimpleNamespace(rfilename='custom_pipeline.py', size=20),
            SimpleNamespace(rfilename='pytorch_model.bin', size=20),
        ])
        selected = module['selected_files'](info)
        self.assertEqual(len(selected), 3)
        info.siblings = [SimpleNamespace(rfilename='model.safetensors', size=None)]
        with self.assertRaises(ValueError):
            module['selected_files'](info)

    def test_existing_changed_preview_is_never_reused_or_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder) / 'preview.mp4'
            video.write_bytes(b'customer-video')
            with self.assertRaises(ValueError):
                module['reusable'](video)
            video.with_suffix('.json').write_text(json.dumps({'fingerprint': module['FINGERPRINT'], 'sha256': 'wrong'}))
            with self.assertRaises(ValueError):
                module['reusable'](video)
            self.assertEqual(video.read_bytes(), b'customer-video')

    def test_explorer_path_is_a_valid_wsl_unc_path(self):
        with contextlib.redirect_stdout(io.StringIO()) as captured:
            module['print_output'](Path('/home/rhod/.local/share/dhanz-rog/outputs/preview.mp4'))
        self.assertIn(chr(92)*2 + 'wsl.localhost' + chr(92) + 'Ubuntu-24.04' + chr(92) + 'home', captured.getvalue())

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg integration check')
    def test_real_mp4_validation_and_reuse_without_model_generation(self):
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder) / 'codec-test.mp4'
            subprocess.run(  # noqa: S603 - fixed synthetic codec-test source, not an AI preview
                ['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=blue:s=512x288:r=16:d=5',
                 '-c:v', 'libx264', '-threads', '1', '-pix_fmt', 'yuv420p', str(video)], check=True
            )
            result = module['validate_video'](video)
            self.assertEqual(result['frames'], 80)
            self.assertAlmostEqual(result['duration_seconds'], 5, places=1)
            video.with_suffix('.json').write_text(json.dumps({
                'fingerprint': module['FINGERPRINT'], 'sha256': hashlib.sha256(video.read_bytes()).hexdigest()
            }))
            self.assertTrue(module['reusable'](video))
            short = Path(folder) / 'short.mp4'
            subprocess.run(  # noqa: S603 - fixed incomplete codec-test source
                ['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=blue:s=512x288:r=16:d=1',
                 '-c:v', 'libx264', '-threads', '1', '-pix_fmt', 'yuv420p', str(short)], check=True
            )
            with self.assertRaises(ValueError):
                module['validate_video'](short)


if __name__ == '__main__':
    unittest.main()
