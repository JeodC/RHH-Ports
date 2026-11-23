"""
.sources parsing, shared by Pharos and the daemon
"""
import re

_GITHUB_REPO = re.compile(
    r"https?://(?:www\.)?github\.com/([A-Za-z0-9-]+)/([A-Za-z0-9._-]+?)(?:\.git)?/?",
    re.IGNORECASE,
)


def read_sources(path, warn=print) -> list[tuple[str, str]]:
    """Returns [(owner, repo)] from a .sources file, one GitHub repo URL per
    line. Lines that aren't one are reported through warn and skipped."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    # utf-8-sig drops the BOM Notepad adds
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        for line in f:
            url = line.strip()
            if not url or url.startswith("#"):
                continue
            match = _GITHUB_REPO.fullmatch(url)
            if not match:
                warn(f"Skipping {ascii(url)}: expected https://github.com/<owner>/<repo>")
                continue
            owner, name = match.groups()
            key = f"{owner}/{name}".lower()
            if key not in seen:
                seen.add(key)
                out.append((owner, name))
    return out
