"""Validate publishable guide targets, excluding ignored runtime artifacts."""

import re
import subprocess
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

import pytest


ROOT = Path(__file__).resolve().parents[1]
GUIDES = [
    ROOT / "README.md",
    *sorted((ROOT / "docs").glob("*.md")),
    *sorted((ROOT / ".old" / "docs").glob("*.md")),
]


def _published_targets(root: Path, tracked_files: set[str]) -> set[str]:
    """Include existing tracked files and their directories, excluding local artifacts."""
    targets: set[str] = set()
    for name in tracked_files:
        path = PurePosixPath(name)
        if path.suffix.lower() in {".txt", ".pkl"} or not (root / name).is_file():
            continue
        targets.add(path.as_posix())
        targets.update(parent.as_posix() for parent in path.parents)
    return targets


@pytest.fixture(scope="module")
def published_targets() -> set[str]:
    # Include new non-ignored source files during development without staging
    # user changes. Ignore generated local artifacts even if they exist on disk.
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="surrogateescape",
        timeout=10,
    )
    tracked_files = set(result.stdout.split("\0")) - {""}
    assert tracked_files, "Documentation validation requires a populated Git index"
    return _published_targets(ROOT, tracked_files)


@pytest.mark.parametrize("guide", GUIDES, ids=lambda path: path.relative_to(ROOT).as_posix())
def test_local_documentation_targets_exist(guide: Path, published_targets: set[str]) -> None:
    text = guide.read_text(encoding="utf-8")
    text = re.sub(r"```.*?```|<!--.*?-->", "", text, flags=re.DOTALL)
    targets = re.findall(r"\[[^\]]*\]\(([^)]+)\)", text)
    targets += re.findall(r'''(?:src|href)=["']([^"']+)["']''', text)
    missing = []
    for target in targets:
        target = target.strip()
        if target.startswith("<"):
            target = target[1:target.index(">")]
        target = re.split(r'''\s+["']''', target, maxsplit=1)[0]
        url = urlsplit(target)
        if url.scheme or url.netloc or not url.path:
            continue
        resolved = (guide.parent / unquote(url.path)).resolve()
        if not resolved.is_relative_to(ROOT):
            missing.append(target)
        elif resolved.relative_to(ROOT).as_posix() not in published_targets:
            missing.append(target)
    assert not missing, (
        f"Missing, untracked, or local-only links in {guide.relative_to(ROOT)}: {missing}"
    )


def test_guides_have_no_duplicate_entries() -> None:
    assert len(GUIDES) == len(set(GUIDES))


def test_root_readme_is_the_only_published_readme(published_targets: set[str]) -> None:
    readmes = {name for name in published_targets if PurePosixPath(name).name.lower() == "readme.md"}
    assert readmes == {"README.md"}


def test_published_targets_require_tracked_files(tmp_path: Path) -> None:
    samples = tmp_path / "samples"
    samples.mkdir()
    (samples / "chart.svg").write_text("<svg/>", encoding="utf-8")
    (samples / "untracked.csv").write_text("date,close\n", encoding="utf-8")
    targets = _published_targets(tmp_path, {"samples/chart.svg", "samples/missing.csv"})
    assert targets == {".", "samples", "samples/chart.svg"}
    # A local directory containing only untracked files is not published either.
    assert _published_targets(tmp_path, set()) == set()


@pytest.mark.parametrize("suffix", [".txt", ".pkl", ".TXT", ".PKL"])
def test_local_artifacts_never_make_a_target_publishable(tmp_path: Path, suffix: str) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    name = f"reports/generated{suffix}"
    (tmp_path / name).write_bytes(b"local artifact")
    # Reject local artifacts even before a pending history/index cleanup finishes.
    assert _published_targets(tmp_path, {name}) == set()