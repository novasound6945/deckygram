"""Running system binaries from inside a frozen plugin.

Decky's loader is packed with PyInstaller, which unpacks its own copy of
libstdc++ and friends into /tmp/_MEIxxxxxx and points LD_LIBRARY_PATH at
it.  Child processes inherit that, so the system ffmpeg was loading
PyInstaller's libraries instead of the ones it was built against:

    ffmpeg: /tmp/_MEI.../libstdc++.so.6: version `GLIBCXX_3.4.32' not
    found (required by /usr/lib/librubberband.so.3)

Seen on Decky Loader v3.2.9 (2026-09-15), where it silently took out
every clip: no posters in the gallery, and no clip could be exported or
encoded either.  Nothing about it is specific to that release - it is
how PyInstaller has always worked - so every external command goes
through here rather than through subprocess directly.

PyInstaller keeps the original value under LD_LIBRARY_PATH_ORIG, so
restoring that hands the binary back the system it expects.
"""

import os
import subprocess


def env() -> dict:
    """The environment a system binary should be started with."""
    clean = dict(os.environ)
    original = clean.pop("LD_LIBRARY_PATH_ORIG", None)
    if original:
        clean["LD_LIBRARY_PATH"] = original
    else:
        clean.pop("LD_LIBRARY_PATH", None)
    return clean


def run(cmd, **kw):
    """subprocess.run, with the loader's own libraries kept out of it."""
    kw.setdefault("env", env())
    return subprocess.run(cmd, **kw)


def popen(cmd, **kw):
    """subprocess.Popen, same reasoning as run()."""
    kw.setdefault("env", env())
    return subprocess.Popen(cmd, **kw)
