"""
sources.json and catalog parsing, shared by Pharos and the daemon
"""

import json
import re

_GITHUB_REPO = re.compile(
    r"(?:(?:https?://)?(?:www\.)?github\.com/)?([A-Za-z0-9-]+/[A-Za-z0-9._-]+)",
    re.IGNORECASE,
)
# GitLab groups can nest
_GITLAB_REPO = re.compile(
    r"(?:https?://)?(?:www\.)?gitlab\.com/([A-Za-z0-9_][A-Za-z0-9._-]*(?:/[A-Za-z0-9_][A-Za-z0-9._-]*)+)",
    re.IGNORECASE,
)
GITLAB = "gitlab.com/"
_FILE_NAME = re.compile(r"[^/\\\x00-\x1f]+")

# Their catalogs are release assets, not files in the repo. The first one hosts
# the runtimes of both.
PORTMASTER_REPOS = ("portsmaster/portmaster-new", "portsmaster-mv/portmaster-mv-new")
DEFAULT_REPOS = (
    "JeodC/RHH-Ports",
    "JeodC/RHH-Wine",
    "NextOs-Ports/nextos-universal-ports",
    "PortsMaster/PortMaster-New",
    "PortsMaster-MV/PortMaster-MV-New",
)


def parse_repo(repo) -> str | None:
    """A repo's slug: owner/name on GitHub, gitlab.com/group/name on GitLab"""
    if not isinstance(repo, str):
        return None
    repo = repo.strip().rstrip("/").removesuffix(".git")
    if match := _GITHUB_REPO.fullmatch(repo):
        return match.group(1)
    if match := _GITLAB_REPO.fullmatch(repo):
        return GITLAB + match.group(1)
    return None


def entry_slug(entry) -> str | None:
    return parse_repo(entry.get("repo")) if isinstance(entry, dict) else None


def repo_address(slug: str) -> str:
    """The reverse of parse_repo"""
    return f"https://{slug}" if slug.startswith(GITLAB) else slug


def load_entries(path) -> list:
    # utf-8-sig drops the BOM Notepad adds
    with open(path, "r", encoding="utf-8-sig", errors="surrogateescape") as f:
        entries = json.load(f)
    if not isinstance(entries, list):
        raise ValueError("not a list")
    return entries


def read_sources(path, warn=print) -> list[str]:
    """Slugs of the enabled entries in a sources.json"""
    out: list[str] = []
    seen: set[str] = set()
    for entry in load_entries(path):
        slug = entry_slug(entry)
        if not slug:
            warn(f"Skipping {ascii(entry)}: expected a GitHub or GitLab repo")
            continue
        if entry.get("enabled", True) and slug.lower() not in seen:
            seen.add(slug.lower())
            out.append(slug)
    return out


def is_portmaster(slug: str) -> bool:
    return slug.lower() in PORTMASTER_REPOS


def _portmaster_catalog(slug: str) -> str:
    return f"https://github.com/{slug}/releases/latest/download/ports.json"


def release_url(slug: str, tag: str) -> str:
    if slug.startswith(GITLAB):
        return f"https://{slug}/-/releases/{tag}/downloads"
    return f"https://github.com/{slug}/releases/download/{tag}"


def runtime_catalog_urls(slug: str) -> list[str]:
    if is_portmaster(slug):
        return [_portmaster_catalog(s) for s in dict.fromkeys((slug.lower(), PORTMASTER_REPOS[0]))]
    return [f"{release_url(slug, 'ports-latest')}/ports.json"]


def catalog_urls(slug: str, filename: str = "ports.json") -> list[str]:
    if is_portmaster(slug):
        return [_portmaster_catalog(slug)] if filename == "ports.json" else []
    # HEAD is the default branch
    base = f"https://{slug}/-/raw/HEAD" if slug.startswith(GITLAB) else f"https://raw.githubusercontent.com/{slug}/HEAD"
    return [f"{base}/docs/{filename}", f"{base}/{filename}"]


def catalog_entries(raw: bytes, key: str = "ports") -> list[dict]:
    """A catalog's entries, each with a name, a source dict and an attr dict"""
    data = json.loads(raw)
    if isinstance(data, dict):
        data = data.get(key, [])
    if isinstance(data, dict):
        data = list(data.values())
    if not isinstance(data, list):
        raise ValueError(f"no {key} list")
    # A name becomes a file name
    entries = [
        e for e in data if isinstance(e, dict) and isinstance(e.get("name"), str) and _FILE_NAME.fullmatch(e["name"])
    ]
    for e in entries:
        for field in ("source", "attr"):
            if not isinstance(e.get(field), dict):
                e[field] = {}
    return entries
