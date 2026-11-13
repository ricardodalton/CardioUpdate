"""Run browser speech-controller regressions in the existing CI test suite."""
import shutil
import subprocess
import unittest
from pathlib import Path


class BriefingAudioTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node.js is needed for browser controller checks')
    def test_speech_controller(self):
        script = Path(__file__).with_suffix('.js')
        result = subprocess.run(['node', str(script)], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
