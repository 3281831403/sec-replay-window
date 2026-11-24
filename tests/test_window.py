"""Strict behavior tests for the anti-replay window.

Exactly 15 tests: 10 map to the 10 documented defects, 5 are cross checks.
The tests treat the window functions as pure: every call returns a new
state dict and never mutates its input.
"""

from replay.window import (
    accept,
    init_window,
    mark,
    mask_for,
    seen,
    shift_window,
    validate_window,
    window_batch,
)


def _state(size=8, max_seq=0, bitmap=0, accepted=0, rejected=0):
    return {
        "size": size,
        "max_seq": max_seq,
        "bitmap": bitmap,
        "accepted": accepted,
        "rejected": rejected,
    }


def test_mask_for_clamps_shift_beyond_width():
    # Defect 1: a shift wider than the window must clamp, not turn all ones.
    assert mask_for(8, 3) == 0b111
    assert mask_for(8, 8) == 0xFF
    assert mask_for(8, 12) == 0xFF
    assert mask_for(8, 100) == 0xFF
    assert mask_for(8, -3) == 0
    assert mask_for(1, 9) == 1


def test_shift_window_clears_moved_out_bits():
    # Defect 2: slots that leave the window must not stay marked.
    w = init_window(4)
    for seq in (1, 2, 3, 4):
        w = accept(w, seq)["state"]
    assert w["bitmap"] == 0b1111
    shifted = shift_window(w, 2)
    assert shifted["max_seq"] == 6
    assert shifted["size"] == 4
    assert shifted["bitmap"] == 0b1100
    assert shifted["bitmap"].bit_length() <= 4
    assert shifted["accepted"] == 4
    assert shifted["rejected"] == 0


def test_shift_window_back_is_logical_not_arithmetic():
    # Defect 3: moving back must discard high slots, never sign extend.
    w = _state(size=16, max_seq=16, bitmap=0xFFFF, accepted=16)
    back = shift_window(w, -4)
    assert back["max_seq"] == 12
    assert back["bitmap"] == 0x0FFF
    assert back["bitmap"] >= 0
    small = shift_window(_state(size=8, max_seq=8, bitmap=0b10000001), -1)
    assert small["max_seq"] == 7
    assert small["bitmap"] == 0b01000000


def test_mark_duplicate_is_idempotent():
    # Defect 4: marking twice must set the bit, never flip it back off.
    w = init_window(8)
    w = accept(w, 1)["state"]
    w = accept(w, 3)["state"]
    assert w["bitmap"] == 0b101
    first = mark(w, 2)
    second = mark(first, 2)
    assert first["bitmap"] == 0b111
    assert seen(first, 2) is True
    assert seen(second, 2) is True
    assert first == second


def test_old_outside_window_sequence_rejected():
    # Defect 5: an old sequence below the window is always rejected, and a
    # repeated sequence inside the window is rejected as well.
    w = init_window(4)
    for seq in (1, 2, 3, 4, 5):
        w = accept(w, seq)["state"]
    assert w["max_seq"] == 5
    assert w["bitmap"] == 0b1111
    assert seen(w, 1) is True
    old = accept(w, 1)
    assert old["accepted"] is False
    assert old["state"]["rejected"] == 1
    assert old["state"]["bitmap"] == w["bitmap"]
    duplicate = accept(w, 4)
    assert duplicate["accepted"] is False
    assert duplicate["state"]["rejected"] == 1
    assert seen(w, 4) is True


def test_jump_advance_clears_intermediate_bits():
    # Defect 6: a forward jump must leave every skipped slot at zero.
    w = init_window(8)
    w = accept(w, 2)["state"]
    w = accept(w, 9)["state"]
    assert w["max_seq"] == 9
    assert w["bitmap"] == 0b10000001
    assert w["bitmap"].bit_length() <= 8
    for seq in range(3, 9):
        assert (w["bitmap"] >> (9 - seq)) & 1 == 0
    nxt = accept(w, 5)
    assert nxt["accepted"] is True
    assert seen(nxt["state"], 5) is True


def test_boundary_sequence_inside_window():
    # Defect 7: max_seq - size + 1 is the boundary and must stay legal.
    w = init_window(4)
    for seq in (2, 3, 4):
        w = accept(w, seq)["state"]
    assert w["max_seq"] == 4
    assert w["bitmap"] == 0b111
    boundary = w["max_seq"] - w["size"] + 1
    assert boundary == 1
    res = accept(w, boundary)
    assert res["accepted"] is True
    assert res["state"]["bitmap"] == 0b1111
    assert seen(res["state"], 1) is True
    assert accept(w, 4)["accepted"] is False


def test_init_window_starts_empty():
    # Defect 8: a fresh window must have an all zero bitmap and max_seq 0.
    w = init_window(8)
    assert w == _state(size=8, max_seq=0, bitmap=0)
    assert seen(w, 1) is False
    first = accept(w, 1)
    assert first["accepted"] is True
    assert first["state"]["bitmap"] == 1


def test_validate_window_checks_bitmap_length():
    # Defect 9: validation must report bitmap width and negative max_seq.
    assert validate_window(init_window(4), 4) == []
    bad = _state(size=4, max_seq=2, bitmap=1 << 4)
    assert validate_window(bad, 4) == ["bitmap_size_mismatch"]
    neg = _state(size=4, max_seq=-1, bitmap=0)
    assert validate_window(neg, 4) == ["max_seq_negative"]
    full = _state(size=4, max_seq=4, bitmap=0b1111, accepted=4)
    assert validate_window(full, 4) == []


def test_batch_isolates_connections():
    # Defect 10: every connection owns an independent window state.
    result = window_batch([("a", 1), ("b", 1), ("a", 1), ("b", 2)], 4)
    assert result["a"]["accepted"] == 1
    assert result["a"]["rejected"] == 1
    assert result["a"]["bitmap"] == 0b1
    assert result["b"]["accepted"] == 2
    assert result["b"]["rejected"] == 0
    assert result["b"]["bitmap"] == 0b11


def test_marked_sequence_is_seen():
    w = init_window(8)
    w = accept(w, 1)["state"]
    w = accept(w, 3)["state"]
    assert w["bitmap"] == 0b101
    assert seen(w, 2) is False
    marked = mark(w, 2)
    assert seen(marked, 2) is True
    assert marked["bitmap"] == 0b111


def test_new_higher_sequence_accepted():
    w = init_window(8)
    for seq in (1, 2, 3, 4):
        w = accept(w, seq)["state"]
    res = accept(w, 5)
    assert res["accepted"] is True
    assert res["state"]["max_seq"] == 5
    assert res["state"]["bitmap"] == 0b11111
    assert seen(res["state"], 5) is True
    assert res["state"]["accepted"] == 5


def test_sequence_below_window_rejected():
    w = init_window(4)
    for seq in (1, 2, 3, 4, 8):
        w = accept(w, seq)["state"]
    assert w["max_seq"] == 8
    assert w["bitmap"] == 0b1
    assert seen(w, 4) is True
    res = accept(w, 4)
    assert res["accepted"] is False
    assert res["state"]["rejected"] == 1
    assert res["state"]["max_seq"] == 8
    assert res["state"]["bitmap"] == 0b1


def test_jump_intermediate_sequences_not_seen():
    w = init_window(8)
    w = accept(w, 2)["state"]
    w = accept(w, 10)["state"]
    assert w["max_seq"] == 10
    assert w["bitmap"] == 0b1
    for seq in range(4, 10):
        assert seen(w, seq) is False
    assert accept(w, 3)["accepted"] is True


def test_batch_matches_individual_processing():
    events = [("a", 1), ("b", 1), ("a", 1), ("b", 2), ("c", 3), ("a", 3)]
    batch = window_batch(events, 4)
    manual = {}
    for conn, seq in events:
        base = manual.get(conn)
        if base is None:
            base = init_window(4)
        manual[conn] = accept(base, seq)["state"]
    assert batch == manual
    assert batch["a"]["accepted"] == 2
    assert batch["a"]["rejected"] == 1
    assert batch["a"]["bitmap"] == 0b101
    assert batch["b"]["bitmap"] == 0b11
    assert batch["c"]["bitmap"] == 0b1