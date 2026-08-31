"""Make py_modules importable from the tests, wherever they are run from."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py_modules"))
