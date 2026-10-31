"""
MSCS 532 - Project (Phase 1)
EmuCache: the dynamic recompiler core.

Ties together the LRU cache, the SMC watcher, and the guest
machine: dispatch loops through the cache, translates blocks on
miss, and invalidates cached blocks when the guest modifies its
own code.

TODO: implement Emulator.
"""


class Emulator:
    """Dynamic recompiler over the toy guest machine. TODO: implement."""

    def __init__(self, guest, cache_capacity=8):
        self.guest = guest
        self.cache_capacity = cache_capacity
