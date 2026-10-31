"""
MSCS 532 - Project (Phase 1)
EmuCache: block translation cache data structures.

A dynamic game emulator translates guest code into basic blocks
and caches the results. This module holds the two core structures:

  HashTable  - open-addressing table (linear probing, rehashing)
  LRUCache   - bounded cache built from HashTable + a doubly
               linked list, with LRU eviction

TODO: implement both structures.
"""


class HashTable:
    """Open-addressing hash table. TODO: implement."""

    def __init__(self, capacity=16):
        self._capacity = capacity


class LRUCache:
    """Bounded LRU cache. TODO: implement."""

    def __init__(self, capacity=8):
        self._capacity = capacity
