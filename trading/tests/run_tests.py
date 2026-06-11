from __future__ import annotations

import importlib.util
import inspect
import sys
from collections.abc import Callable, Iterator
from pathlib import Path


TEST_DIR = Path(__file__).resolve().parent
TRADING_ROOT = TEST_DIR.parents[0]
sys.path.insert(0, str(TRADING_ROOT))
sys.path.insert(0, str(TEST_DIR))


def _load_module(path: Path):
    module_name = path.stem
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _iter_tests() -> Iterator[Callable[[], None]]:
    for path in sorted(TEST_DIR.glob("test_*.py")):
        module = _load_module(path)
        for name, test in sorted(inspect.getmembers(module, inspect.isfunction)):
            if name.startswith("test_"):
                yield test


def main() -> int:
    tests = list(_iter_tests())
    for test in tests:
        test()
        print(f"PASS {test.__module__}.{test.__name__}")
    print(f"ran {len(tests)} tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
