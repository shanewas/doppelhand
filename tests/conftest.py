import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
# Test the checkout, not whatever doppelhand is pip-installed.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
