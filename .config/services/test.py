# /// script
# requires-python = ">=3.13"
# dependencies = ["PyYAML==6.0.3"]
# ///
"""Run controller and service tests."""
from pathlib import Path
import unittest

root = Path(__file__).resolve().parent
suite = unittest.TestSuite()
suite.addTests(unittest.TestLoader().discover(str(root / "tests")))
for directory in sorted((root / "definitions").iterdir()):
    if directory.is_dir() and any(directory.glob("test_*.py")):
        suite.addTests(unittest.TestLoader().discover(str(directory)))
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(not result.wasSuccessful())
