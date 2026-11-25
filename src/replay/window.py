"""Anti-replay sliding window core.

All functions are pure: they return a new state dict and never mutate the
input state.  A state is a plain dict with these fields:

    size      window width in slots, at least 1
    max_seq   highest sequence number accepted so far, 0 means none
    bitmap    integer bitmask; bit i is set when max_seq - i was used
    accepted  number of accepted sequence numbers so far
    rejected  number of rejected sequence numbers so far

Window contract:

    The window covers max_seq - size + 1 through max_seq, both boundaries
    included.  A sequence above max_seq advances the window and clears every
    slot that leaves it.  A sequence below the window is old and therefore
    treated as already seen.  Marking is idempotent, and each connection in a
    batch owns an independent window.
"""


def init_window(size: int) -> dict:
    """Return a fresh window of the given width with all bits zero."""
    return {
        "size": size,
        "max_seq": 0,
        "bitmap": 0,
        "accepted": 0,
        "rejected": 0,
    }


def mask_for(size: int, shift: int) -> int:
    """Return a low bit mask of shift bits, clamped to the window width."""
    if size < 0:
        size = 0
    if shift < 0:
        shift = 0
    elif shift > size:
        shift = size
    return (1 << shift) - 1


def shift_window(state: dict, delta: int) -> dict:
    """Move the whole window by delta slots, clearing every moved out bit."""
    size = state["size"]
    full = mask_for(size, size)

    if delta > 0:
        # Slots move to higher bit indices; anything past the width leaves
        # the window and must be discarded rather than kept as stale history.
        bitmap = (state["bitmap"] << delta) & full
        max_seq = state["max_seq"] + delta
    elif delta < 0:
        step = -delta
        # Python's right shift on a non-negative int is a logical shift, so a
        # backward move drops the high slots without sign extension.
        bitmap = (state["bitmap"] >> step) & full
        max_seq = state["max_seq"] - step
        if max_seq < 0:
            max_seq = 0
            bitmap = 0
    else:
        bitmap = state["bitmap"] & full
        max_seq = state["max_seq"]

    shifted = dict(state)
    shifted["max_seq"] = max_seq
    shifted["bitmap"] = bitmap
    return shifted


def mark(state: dict, seq: int) -> dict:
    """Mark seq as used; marking the same sequence again is idempotent."""
    marked = dict(state)
    index = state["max_seq"] - seq
    if seq <= state["max_seq"] and 0 <= index < state["size"]:
        # OR, never XOR: marking an already seen sequence must not clear it.
        marked["bitmap"] = state["bitmap"] | (1 << index)
    return marked


def seen(state: dict, seq: int) -> bool:
    """Report whether seq was used; old sequences below the window count as seen."""
    if seq > state["max_seq"]:
        return False
    index = state["max_seq"] - seq
    if index >= state["size"]:
        # Below the lower boundary max_seq - size + 1: the window no longer
        # tracks it, so it is old and can only be treated as already seen.
        return True
    return bool((state["bitmap"] >> index) & 1)


def accept(state: dict, seq: int) -> dict:
    """Decide one sequence and advance the window when it is new and higher."""
    lower = state["max_seq"] - state["size"] + 1

    if seq < lower:
        # Old packet below the window: always rejected, state untouched.
        rejected = dict(state)
        rejected["rejected"] = state["rejected"] + 1
        return {"accepted": False, "state": rejected}

    if seq > state["max_seq"]:
        # Advance the window in one jump.  shift_window clears the slots that
        # leave the window and leaves every skipped intermediate slot at 0.
        advanced = shift_window(state, seq - state["max_seq"])
        advanced = mark(advanced, seq)
        advanced["accepted"] = state["accepted"] + 1
        return {"accepted": True, "state": advanced}

    index = state["max_seq"] - seq
    if (state["bitmap"] >> index) & 1:
        duplicate = dict(state)
        duplicate["rejected"] = state["rejected"] + 1
        return {"accepted": False, "state": duplicate}

    accepted_state = mark(state, seq)
    accepted_state["accepted"] = state["accepted"] + 1
    return {"accepted": True, "state": accepted_state}


def validate_window(state: dict, size: int) -> list[str]:
    """Return the list of structural problems found in a window state."""
    problems = []
    bitmap = state["bitmap"]

    if bitmap < 0 or bitmap.bit_length() > size:
        problems.append("bitmap_size_mismatch")
    if state["max_seq"] < 0:
        problems.append("max_seq_negative")
    if mask_for(size, size).bit_length() > size:
        problems.append("mask_overflow")
    return problems


def window_batch(events, size: int) -> dict:
    """Process (connection, sequence) events, one independent window per connection."""
    windows = {}
    for connection, seq in events:
        state = windows.get(connection)
        if state is None:
            state = init_window(size)
        windows[connection] = accept(state, seq)["state"]
    return windows
