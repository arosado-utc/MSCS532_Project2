"""
MSCS 532 - Project (Phase 1)
EmuCache: self-modifying code (SMC) page watcher.

Watches guest memory pages: when the guest writes to a page that
holds translated code, every cached block on that page must be
invalidated and retranslated.

TODO: implement PageWatcher.
"""


class PageWatcher:
    """Page-granularity SMC watcher. TODO: implement."""

    def __init__(self, page_size=32):
        self.page_size = page_size
