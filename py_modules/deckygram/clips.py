"""Turning Steam's DASH clip folders into something ffmpeg can remux.

Steam stores a clip as fragmented MP4: one `init-stream<N>.m4s` header
per track, then `chunk-stream<N>-00001.m4s` onwards, roughly three
seconds apiece, described by a `session.mpd` manifest.

The obvious remux - `ffmpeg -i session.mpd -c copy out.mp4` - is wrong,
and wrong in a way that hides.  A clip that covers only PART of a
recording session keeps its offset into that session's timeline:

    <Period id="0" start="PT27.739S">

ffmpeg's DASH demuxer honours that offset by emitting a single segment,
so a 60-second clip comes out three seconds long - with exit code 0 and
a perfectly valid file.  Measured on a Steam Deck (2026-09-14) across 74
clips: all 71 with `start="PT0.0S"` remuxed to their full length, and
all 3 with a non-zero start came out at exactly 3 s.

Background recording is the obvious way to end up with such a clip - a
rolling buffer is always longer than the slice you keep - and both
background clips in that set were affected.  But it is the slicing that
does it, not the mode: one manually recorded clip out of 72 was also
short, a 59-second window starting 1:05 into a five-minute session.  A
manual recording is merely *usually* kept whole, which is why this took
so long to surface.

So the manifest is read for its duration and nothing else.  Fragments go
to ffmpeg directly through the `concat:` protocol - sound because
fragmented MP4 is designed to be joined byte-wise, and it needs no temp
files and no writes into Steam's own folders.  SteamClip reaches the
same conclusion by a different route, stitching the fragments by hand.
"""

import glob
import os
import re

INIT_RE = re.compile(r"^init-stream(\d+)\.m4s$")
CHUNK_RE = re.compile(r"^chunk-stream(\d+)-(\d+)\.m4s$")


def streams(chunk_dir: str):
    """Track indexes present, ascending.  Steam writes 0=video, 1=audio."""
    found = []
    for path in glob.glob(os.path.join(chunk_dir, "init-stream*.m4s")):
        m = INIT_RE.match(os.path.basename(path))
        if m:
            found.append(int(m.group(1)))
    return sorted(found)


def chunks(chunk_dir: str, index: int):
    """Fragments of one track in recording order.

    Sorted on the parsed number rather than the name: the counter is
    zero-padded today, and nothing says it has to stay that way past
    99999 fragments.
    """
    numbered = []
    for path in glob.glob(os.path.join(chunk_dir,
                                       "chunk-stream%d-*.m4s" % index)):
        m = CHUNK_RE.match(os.path.basename(path))
        if m:
            numbered.append((int(m.group(2)), path))
    return [p for _, p in sorted(numbered)]


def concat_spec(chunk_dir: str, index: int):
    """`concat:` input for one track, or None when it has no fragments."""
    init = os.path.join(chunk_dir, "init-stream%d.m4s" % index)
    parts = chunks(chunk_dir, index)
    if not parts or not os.path.exists(init):
        return None
    return "concat:" + "|".join([init] + parts)


def ffmpeg_inputs(chunk_dir: str):
    """One `concat:` input per track, video first - empty when unusable."""
    specs = []
    for index in streams(chunk_dir):
        spec = concat_spec(chunk_dir, index)
        if spec:
            specs.append(spec)
    return specs
