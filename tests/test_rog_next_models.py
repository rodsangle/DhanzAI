import contextlib
import io
import runpy
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "apps/rog_video_worker/setup_next_models.py"
module = runpy.run_path(str(SCRIPT))


class NextModelsTests(unittest.TestCase):
    def test_plan_only_by_default_and_changes_nothing(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch("subprocess.run") as run:
            self.assertEqual(module["main"]([]), 0)
        run.assert_not_called()
        text = out.getvalue()
        self.assertIn("Z-Image-Turbo", text)
        self.assertIn("Wan 2.2 TI2V-5B", text)
        self.assertIn("not changed", text)

    def test_refuses_root_or_missing_amd_environment(self):
        with mock.patch("os.geteuid", return_value=1000), mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "amd-env.sh"):
                module["main"](["--apply"])

    def test_only_data_files_are_downloaded(self):
        info = SimpleNamespace(
            siblings=[
                SimpleNamespace(rfilename="transformer/diffusion_pytorch_model.safetensors", size=10),
                SimpleNamespace(rfilename="tokenizer/tokenizer.json", size=1),
                SimpleNamespace(rfilename="tokenizer/merges.txt", size=1),
                SimpleNamespace(rfilename="pipeline.py", size=1),
                SimpleNamespace(rfilename="model.bin", size=1),
            ]
        )
        self.assertEqual(len(module["selected_files"](info)), 3)
        info.siblings = [SimpleNamespace(rfilename="model.bin", size=1)]
        with self.assertRaisesRegex(ValueError, "no safe tensor"):
            module["selected_files"](info)

    def test_pins_are_separate_per_model_and_libraries_are_pinned(self):
        self.assertEqual(
            module["pin_name"]("Wan-AI/Wan2.2-TI2V-5B-Diffusers"), "revision-wan-ai-wan2-2-ti2v-5b-diffusers.json"
        )
        self.assertNotEqual(module["pin_name"](module["VIDEO"]["model"]), module["pin_name"](module["PHOTO"]["model"]))
        self.assertTrue(all("==" in package for package in module["PACKAGES"]))
        self.assertEqual(module["TORCH"]["TORCH_VERSION"], "2.11.0+rocm7.2")

    def test_video_spec_matches_wan22_requirements(self):
        video = module["VIDEO"]
        self.assertEqual((video["frames"] - 1) % 4, 0)  # Wan expects 4k+1 frames
        self.assertEqual(video["width"] % 32, 0)
        self.assertEqual(video["height"] % 32, 0)
        self.assertAlmostEqual(video["frames"] / video["fps"], 5.04, places=2)

    def test_gpu_check_never_touches_the_workers_marker(self):
        source = SCRIPT.read_text()
        self.assertIn("'--state-dir', str(OUT)", source)
        self.assertNotIn("'--state-dir', str(STATE)", source)


if __name__ == "__main__":
    unittest.main()
