"""
MSCS 532 - Project (Phase 1)
EmuCache: self-modifying code (SMC) page watcher.

Real console games and homebrew software sometimes write to their
own code at runtime (level patches, demos that rewrite their main
loop). A cached translation of such code is stale the moment the
bytes change, so the emulator must watch memory for writes and
evict the affected blocks.

This module tracks watched regions at PAGE granularity: each
cached block registers the code pages it covers, and a write to a
page returns the set of block IDs that page contains. Page
granularity is a trade-off - per-byte tracking costs
O(n) per write, while per-block tracking misses writes to
neighboring code. Pages give an O(1) lookup with bounded
over-invalidation, the same idea QEMU uses for its code-write
protection (Bellard, 2005).
"""


class PageWatcher:
    """Watches guest memory pages for self-modifying writes.

    Maps page number -> set of block IDs whose code covers that
    page. A block that spans a page boundary registers in every
    page it touches.

    Complexity:
        register / unregister  - O(pages covered), usually 1-2
        on_write               - O(1) lookup + O(k) to copy the
                                  set of victim block IDs
    """

    def __init__(self, page_size=32):
        if page_size < 1 or (page_size & (page_size - 1)) != 0:
            raise ValueError("page_size must be a power of two")
        self.page_size = page_size
        self._pages = {}  # page number -> set of block IDs

    def _page_range(self, start, end):
        """Page numbers covered by the half-open range [start, end)."""
        first = start // self.page_size
        last = (end - 1) // self.page_size
        return range(first, last + 1)

    def register(self, block_id, start_pc, end_pc):
        """Remember that block_id covers [start_pc, end_pc)."""
        for page in self._page_range(start_pc, end_pc):
            self._pages.setdefault(page, set()).add(block_id)

    def unregister(self, block_id, start_pc, end_pc):
        """Forget block_id (it left the cache or was invalidated)."""
        for page in self._page_range(start_pc, end_pc):
            ids = self._pages.get(page)
            if ids:
                ids.discard(block_id)
                if not ids:
                    del self._pages[page]

    def on_write(self, addr):
        """Return the set of block IDs invalidated by a write to addr.

        An empty set means the page is not watched - the write is
        just data and nothing in the cache is affected.
        """
        page = addr // self.page_size
        return set(self._pages.get(page, ()))
