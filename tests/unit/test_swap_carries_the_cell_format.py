"""A row swap carries each cell's FORMAT with its contents, in the in-memory store.

``swap_rows`` moved only the text; the formatting stayed on the row the text left, so a swapped
class kept the old row's colouring. The store now records a format per cell (``put_formats`` /
``format_of``, for tests) and the swap moves it with the cell — absence included: a cell with no
format that swaps with one that has it ends up without, and the other with. The fixed (date)
column is never named in ``content_cols`` and stays put.

Formats here are INVENTED opaque tokens — the store never interprets a format, it only carries it.
"""

from __future__ import annotations

from cogno_praxis.coordinator import InMemorySpreadsheetStore


def test_each_rows_format_moves_with_its_content_and_the_fixed_column_stays():
    store = InMemorySpreadsheetStore()
    store.put("SID", "Grade", [
        ["Zarnuk", "Qel-ONE", "Vorth-ONE"],       # grid row 0
        ["Zarnuk", "Qel-TWO", "Vorth-TWO"],       # grid row 1
    ])
    # an invented format per cell; the fixed column 0 carries its own, which must not move
    store.put_formats("SID", "Grade", {
        (0, 0): {"ink": "fixed"},
        (0, 1): {"ink": "crimson"}, (0, 2): {"ink": "crimson"},
        (1, 1): {"ink": "cobalt"}, (1, 2): {"ink": "cobalt"},
    })

    store.swap_rows("SID", "Grade", "A1:C10", 0, 1, content_cols=[1, 2])

    # contents swapped
    assert store.read_range("SID", "Grade", "A1:C10")[0] == ["Zarnuk", "Qel-TWO", "Vorth-TWO"]
    # each content cell's format travelled WITH its content
    assert store.format_of("SID", "Grade", 0, 1) == {"ink": "cobalt"}
    assert store.format_of("SID", "Grade", 0, 2) == {"ink": "cobalt"}
    assert store.format_of("SID", "Grade", 1, 1) == {"ink": "crimson"}
    # the fixed column's format stayed where it was
    assert store.format_of("SID", "Grade", 0, 0) == {"ink": "fixed"}


def test_a_swap_moves_the_absence_of_a_format_like_a_value():
    store = InMemorySpreadsheetStore()
    store.put("SID", "Grade", [["Gorm", "Plin-ONE"], ["Gorm", "Plin-TWO"]])
    store.put_formats("SID", "Grade", {(0, 1): {"ink": "gold"}})   # row 1's cell has none

    store.swap_rows("SID", "Grade", "A1:B10", 0, 1, content_cols=[1])

    assert store.format_of("SID", "Grade", 0, 1) is None           # gave its format away
    assert store.format_of("SID", "Grade", 1, 1) == {"ink": "gold"}


def test_a_store_with_no_recorded_formats_swaps_contents_as_before():
    """The control: a store that never saw ``put_formats`` swaps contents and records nothing —
    the format machinery is inert until a format is put."""
    store = InMemorySpreadsheetStore()
    store.put("SID", "Grade", [["Gorm", "Plin-ONE"], ["Gorm", "Plin-TWO"]])

    store.swap_rows("SID", "Grade", "A1:B10", 0, 1, content_cols=[1])

    assert store.read_range("SID", "Grade", "A1:B10")[0] == ["Gorm", "Plin-TWO"]
    assert store.format_of("SID", "Grade", 0, 1) is None
