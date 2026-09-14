"""The parts of Steam's own configuration that we have to read.

Steam keeps per-user settings in `localconfig.vdf` - quoted keys, each
followed by a value or a nested block. Only one of them matters here so
far: the folder game recordings are written to, which Settings > Game
Recording lets people move to an SD card.

    "GameRecording"
    {
        "BackgroundRecordMode"    "1"
        ...
        "BackgroundRecordPath"    "/run/media/deck/<uuid>/New Folrec"
    }

The key is written only once the folder has been changed, so its absence
means the default under `userdata` - which is why this could not be
discovered by reading a stock install. Steam's own UI is no help either:
it addresses recordings through an internal `steamloopback.host` URL and
never exposes the real path.
"""

import glob
import os
import re

RECORD_PATH_RE = re.compile(r'"BackgroundRecordPath"\s*"((?:[^"\\]|\\.)*)"')


def _unescape(value: str) -> str:
    r"""VDF escapes backslashes and quotes; nothing else is worth handling."""
    return value.replace(r'\"', '"').replace(r'\\', '\\')


def local_configs(home: str):
    """Every user's localconfig.vdf on this machine, in a stable order."""
    return sorted(glob.glob(os.path.join(
        home, ".steam/steam/userdata/*/config/localconfig.vdf")))


# localconfig.vdf is ~400 KB and this is asked on every scan and every
# gallery page, so the answer is kept until the file itself changes.
_CACHE = {}


def recording_path(config_path: str) -> str:
    """The recordings folder named in one localconfig.vdf, or "".

    An unreadable config is not an error worth raising: it just means we
    fall back to the default location, which is where recordings are for
    all but a handful of people.
    """
    try:
        stat = os.stat(config_path)
    except OSError:
        return ""
    stamp = (stat.st_mtime, stat.st_size)
    cached = _CACHE.get(config_path)
    if cached and cached[0] == stamp:
        return cached[1]
    try:
        with open(config_path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return ""
    found = RECORD_PATH_RE.search(text)
    path = _unescape(found.group(1)).strip() if found else ""
    _CACHE[config_path] = (stamp, path)
    return path


def recording_paths(home: str):
    """Custom recordings folders configured on this machine, deduplicated.

    Empty when nobody has moved theirs, which is the common case.
    """
    out = []
    for config in local_configs(home):
        path = recording_path(config)
        if path and path not in out:
            out.append(path)
    return out


def recording_roots(home: str):
    """Every recordings tree on this machine, default and custom alike.

    Steam moves the whole tree when the folder is changed - clips,
    timelines and the clip index all follow - but it leaves what was
    already recorded where it was.  So both places stay interesting, and
    someone who moves their folder does not lose sight of older clips.

    Screenshots are NOT affected: the setting covers recordings only,
    and they keep going to `userdata/<id>/760/remote`.
    """
    roots = glob.glob(os.path.join(
        home, ".steam/steam/userdata/*/gamerecordings"))
    roots.extend(recording_paths(home))
    return sorted(set(roots))


def clip_roots(home: str):
    """The `clips` folder under every recordings root that has one."""
    return [d for d in (os.path.join(root, "clips")
                        for root in recording_roots(home))
            if os.path.isdir(d)]


def clip_dirs(home: str):
    """Every clip folder on this machine, across all roots.

    Listed rather than globbed on purpose: a moved recordings folder is
    a path somebody typed, and a bracket anywhere in it would otherwise
    be read as a glob pattern and match nothing.
    """
    for root in clip_roots(home):
        try:
            names = os.listdir(root)
        except OSError:
            continue
        for name in names:
            path = os.path.join(root, name)
            if os.path.isdir(path):
                yield path
