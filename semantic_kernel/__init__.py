"""Project workflow modules layered over the installed Semantic Kernel SDK."""

from importlib.machinery import PathFinder
from pathlib import Path
import sys

_LOCAL_PACKAGE = Path(__file__).resolve().parent
_PROJECT_ROOT = _LOCAL_PACKAGE.parent.resolve()
_external_spec = PathFinder.find_spec(
    __name__,
    [entry for entry in sys.path if Path(entry or ".").resolve() != _PROJECT_ROOT],
)
if _external_spec is None or _external_spec.origin is None:
    raise ImportError("The 'semantic-kernel' package must be installed.")

_external_init = Path(_external_spec.origin)
__file__ = str(_external_init)
__path__ = [str(_LOCAL_PACKAGE), str(_external_init.parent)]
exec(compile(_external_init.read_text(encoding="utf-8"), str(_external_init), "exec"))
