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
    raise NotImplementedError("init_window is a stub")


def mask_for(size: int, shift: int) -> int:
    """Return a low bit mask of shift bits, clamped to the window width."""
    raise NotImplementedError("mask_for is a stub")


def shift_window(state: dict, delta: int) -> dict:
    """Move the whole window by delta slots, clearing every moved out bit."""
    raise NotImplementedError("shift_window is a stub")


def mark(state: dict, seq: int) -> dict:
    """Mark seq as used; marking the same sequence again is idempotent."""
    raise NotImplementedError("mark is a stub")


def seen(state: dict, seq: int) -> bool:
    """Report whether seq was used; old sequences below the window count as seen."""
    raise NotImplementedError("seen is a stub")


def accept(state: dict, seq: int) -> dict:
    """Decide one sequence and advance the window when it is new and higher."""
    raise NotImplementedError("accept is a stub")


def validate_window(state: dict, size: int) -> list[str]:
    """Return the list of structural problems found in a window state."""
    raise NotImplementedError("validate_window is a stub")


def window_batch(events, size: int) -> dict:
    """Process (connection, sequence) events, one independent window per connection."""
    raise NotImplementedError("window_batch is a stub")