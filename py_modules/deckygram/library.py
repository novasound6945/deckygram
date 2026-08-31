"""Finding entries Steam still lists after the file behind them is gone.

Deleting a screenshot from disk does not remove it from Steam's screenshot
index, so the media grid draws a tile with a warning triangle where the
picture used to be. Deckygram caused exactly that whenever
delete-after-send was on (reported by a user, 2026-08-31).

Only the client can fix the index - `SteamClient.Screenshots.DeleteLocalScreenshot`
is a frontend API - so the split is: the frontend reads Steam's list and
asks here which of those files are actually missing, then deletes those
entries. This module is the "which are missing" half, kept pure so the
path handling can be tested without a Steam install.

Clips need none of this: Steam enumerates the clips directory itself and
keeps no separate list of them, so removing a clip folder leaves nothing
behind.
"""

import os

# What Steam prefixes its screenshot URLs with. `strUrl` reads
# "screenshots/<appid>/screenshots/<name>.jpg" while the path on disk is
# "<userdata>/<id>/760/remote/<appid>/screenshots/<name>.jpg".
URL_PREFIX = "screenshots/"


def url_to_relpath(url):
    """Steam's strUrl -> the path under a 760/remote root, or None.

    Returns None for anything that would escape the root or is not a
    plain relative path; those are never worth touching.
    """
    if not isinstance(url, str) or not url:
        return None
    rel = url[len(URL_PREFIX):] if url.startswith(URL_PREFIX) else url
    rel = rel.strip().lstrip("/")
    if not rel:
        return None
    parts = [p for p in rel.split("/") if p]
    if not parts or any(p in (".", "..") for p in parts):
        return None
    return os.path.join(*parts)


def find_orphans(urls, remote_roots):
    """Return the subset of `urls` whose file is gone from every root.

    A URL is only reported when at least one root could actually answer
    the question - that is, the directory the file belongs in exists. If
    the whole tree is missing (Steam data moved, an account's folder not
    created yet) the entries are left alone rather than mass-deleted from
    the user's library on the strength of an absent mount.
    """
    roots = [r for r in remote_roots if r]
    if not roots:
        return []

    out = []
    for url in urls:
        rel = url_to_relpath(url)
        if rel is None:
            continue
        checkable = False
        found = False
        for root in roots:
            path = os.path.join(root, rel)
            if os.path.isfile(path):
                found = True
                break
            if os.path.isdir(os.path.dirname(path)):
                checkable = True
        if checkable and not found:
            out.append(url)
    return out


def find_missing_clips(clip_ids, clip_roots):
    """Return the clip ids whose folder is gone from every clips root.

    Steam holds its clip list for as long as its UI is up, so clips a past
    session deleted are still listed and draw a broken tile. The frontend
    can tell Steam to forget one, but only knows which after asking here.

    Like find_orphans, this refuses to answer when no clips directory
    exists at all: that reads as "Steam data is not where we expect", not
    as "every clip was deleted".
    """
    roots = [r for r in clip_roots if r and os.path.isdir(r)]
    if not roots:
        return []

    out = []
    for cid in clip_ids:
        if not isinstance(cid, str) or not cid:
            continue
        if cid in (".", "..") or "/" in cid or "\\" in cid:
            continue                     # a clip id is one folder name
        if not any(os.path.isdir(os.path.join(r, cid)) for r in roots):
            out.append(cid)
    return out
