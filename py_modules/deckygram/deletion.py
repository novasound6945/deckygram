"""Deciding what "delete this" means for one item.

Deleting from the gallery is not one action. The same button press has to
do the right thing for a screenshot sitting idle, one that is seconds away
from being uploaded, and one whose file somebody already removed. Getting
it wrong is expensive in both directions: delete a file mid-upload and the
send fails on a file that no longer exists, defer a delete that will never
happen and the user's instruction is quietly dropped.

The rule is small enough to state in full:

  - no file           -> nothing to delete, just forget it   (GONE)
  - being uploaded    -> delete once that finishes           (AFTER_SEND)
  - queued, and sending is actually running -> same          (AFTER_SEND)
  - anything else     -> delete now                          (NOW)

The second and third cases are why this exists. The fourth catches the
cases where deferring would strand the instruction: sending switched off,
a destination that is refusing everything, an item that already gave up.
Those will not drain on their own, so "later" would mean "never".
"""

NOW = "now"
AFTER_SEND = "after_send"
GONE = "gone"


def classify(exists, in_flight=False, pending=False, sending_active=False):
    """What to do about a delete request for one item.

    `exists`         - the file or clip folder is still on disk
    `in_flight`      - the sender is working on it right now
    `pending`        - it is in the queue waiting its turn
    `sending_active` - sending is on and not suspended, so the queue moves
    """
    if not exists:
        return GONE
    if in_flight:
        return AFTER_SEND
    if pending and sending_active:
        return AFTER_SEND
    return NOW


def plan(items, state):
    """Sort a selection into buckets, keeping the caller's order.

    `state(item)` returns the four flags as a dict; anything missing is
    treated as False. Returns {NOW: [...], AFTER_SEND: [...], GONE: [...]}.
    A mixed selection is normal - some tiles idle, some mid-flight - and
    the UI has to be able to tell the user which was which.
    """
    out = {NOW: [], AFTER_SEND: [], GONE: []}
    for item in items:
        s = state(item) or {}
        out[classify(
            exists=bool(s.get("exists")),
            in_flight=bool(s.get("in_flight")),
            pending=bool(s.get("pending")),
            sending_active=bool(s.get("sending_active")),
        )].append(item)
    return out
