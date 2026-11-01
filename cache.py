"""
MSCS 532 - Project (Phase 1)
EmuCache: block translation cache data structures.

A dynamic game emulator translates guest code into basic blocks
and caches the results. Looking up the translated block for a
guest program counter happens once per block dispatch, so the
lookup must be O(1). Two structures are provided:

  HashTable  - open addressing with linear probing, tombstone
               deletion, and rehashing at a 0.7 load factor.
  LRUCache   - a bounded cache built from a HashTable plus a
               doubly linked list, so both "move to most recent"
               and "evict the least recent" are O(1).

The hash function is Knuth's multiplicative hash: the key is
multiplied by a large odd constant and the low bits of the
product are used as the index. Because the constant is odd, the
mapping is a permutation modulo 2^32, which spreads consecutive
program counters (the common case in guest code) across the whole
table instead of clustering them.
"""


class _Node:
    """One entry in the LRU list. The list is what orders the
    cache by recency; the hash table is only how we find it."""

    __slots__ = ("key", "value", "prev", "next")

    def __init__(self, key, value):
        self.key = key
        self.value = value
        self.prev = None
        self.next = None


_TOMBSTONE = object()  # marks a deleted slot; keeps probe chains intact
_MISS = object()       # sentinel for __contains__


class HashTable:
    """Open-addressing hash table (linear probing, tombstones).

    Keys are guest program counters (ints); values are _Node
    objects for the LRU list, though anything works.

    The table size is always a power of two. When live entries
    plus tombstones reach 70% of the table, it rehashes at double
    the size. Tombstones keep probe chains intact but still count
    toward the load factor, so a churn of deletes forces a
    rehash and clears them out.

    Complexity:
        get / put / delete  - O(1) average, O(n) worst case
        rehash              - O(n)
    """

    _LOAD_LIMIT = 0.7
    _MULT = 2654435761  # Knuth's multiplicative constant (32-bit)

    def __init__(self, capacity=16):
        size = 4
        while size < max(4, capacity):
            size <<= 1
        self._size = size
        self._mask = size - 1
        self._keys = [None] * size
        self._vals = [None] * size
        self._tombstones = 0
        self._count = 0

    # hashing and probing
    def _home(self, key):
        """Home slot for key (Knuth multiplicative hash)."""
        return ((key * self._MULT) & 0xFFFFFFFF) & self._mask

    def _probe(self, key):
        """Slot where key lives, or the first empty slot in its
        probe sequence (the spot a new key would be inserted)."""
        slot = self._home(key)
        for _ in range(self._size):
            k = self._keys[slot]
            if k is None or k == key:
                return slot
            slot = (slot + 1) & self._mask
        raise RuntimeError("hash table full")  # unreachable under 0.7 limit

    def _rehash(self, new_size):
        """Rebuild the table with new_size slots, dropping tombstones."""
        old = list(zip(self._keys, self._vals))
        self._size = new_size
        self._mask = new_size - 1
        self._keys = [None] * new_size
        self._vals = [None] * new_size
        self._tombstones = 0
        self._count = 0
        for k, v in old:
            if k is None or k is _TOMBSTONE:
                continue
            slot = self._home(k)
            while self._keys[slot] is not None:
                slot = (slot + 1) & self._mask
            self._keys[slot] = k
            self._vals[slot] = v
            self._count += 1

    # public interface
    def get(self, key, default=None):
        """Return the value for key, or default if the key is absent."""
        slot = self._probe(key)
        if self._keys[slot] == key:
            return self._vals[slot]
        return default

    def put(self, key, value):
        """Insert key -> value, or overwrite the value if key exists."""
        slot = self._probe(key)
        if self._keys[slot] == key:
            self._vals[slot] = value
            return
        if self._count + self._tombstones >= self._LOAD_LIMIT * self._size:
            self._rehash(self._size * 2)
            slot = self._probe(key)
        if self._keys[slot] is _TOMBSTONE:  # reuse the tombstone slot
            self._tombstones -= 1
        self._keys[slot] = key
        self._vals[slot] = value
        self._count += 1

    def delete(self, key):
        """Remove key. Returns True if the key was present."""
        slot = self._probe(key)
        if self._keys[slot] != key:
            return False
        self._keys[slot] = _TOMBSTONE
        self._vals[slot] = None
        self._count -= 1
        self._tombstones += 1
        return True

    def __contains__(self, key):
        return self.get(key, _MISS) is not _MISS

    def __len__(self):
        return self._count


class LRUCache:
    """Bounded cache with least-recently-used eviction.

    A HashTable maps guest PC -> _Node for O(1) lookup, and a
    doubly linked list keeps the entries in recency order: most
    recently used at the head, least at the tail. A hit moves the
    node to the head; an insertion into a full cache pops the tail.

    Complexity:  get / put / remove  -  O(1)
    """

    def __init__(self, capacity=8):
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self._capacity = capacity
        self._table = HashTable(capacity * 4)
        self._head = None  # most recently used
        self._tail = None  # least recently used
        self._size = 0
        self.evictions = 0

    # public interface
    def get(self, key):
        """Return the cached value for key, or None on a miss.
        A hit moves the entry to most-recent."""
        node = self._table.get(key)
        if node is None:
            return None
        self._move_to_front(node)
        return node.value

    def put(self, key, value):
        """Insert (or refresh) an entry. Returns the evicted
        (key, value) pair, or None if nothing was evicted."""
        node = self._table.get(key)
        if node is not None:
            node.value = value
            self._move_to_front(node)
            return None
        node = _Node(key, value)
        self._table.put(key, node)
        self._push_front(node)
        self._size += 1
        if self._size > self._capacity:
            self.evictions += 1
            evicted = self._pop_back()
            return (evicted.key, evicted.value)
        return None

    def remove(self, key):
        """Remove and return the cached value for key, or None."""
        node = self._table.get(key)
        if node is None:
            return None
        self._unlink(node)
        self._table.delete(key)
        self._size -= 1
        return node.value

    def __len__(self):
        return self._size

    # linked-list bookkeeping
    def _push_front(self, node):
        node.prev = None
        node.next = self._head
        if self._head is not None:
            self._head.prev = node
        self._head = node
        if self._tail is None:
            self._tail = node

    def _unlink(self, node):
        if node.prev is not None:
            node.prev.next = node.next
        else:
            self._head = node.next
        if node.next is not None:
            node.next.prev = node.prev
        else:
            self._tail = node.prev
        node.prev = None
        node.next = None

    def _move_to_front(self, node):
        if node is self._head:
            return
        self._unlink(node)
        self._push_front(node)

    def _evict(self):
        """Remove and return the least-recently-used entry (from both
        the list and the hash table)."""
        node = self._tail
        self._unlink(node)
        self._table.delete(node.key)
        self._size -= 1
        return node

    def _pop_back(self):
        return self._evict()
