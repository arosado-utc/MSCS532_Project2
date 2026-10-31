"""
MSCS 532 - Project (Phase 1)
EmuCache: toy guest machine and block decoder.

A tiny register machine with an 8-bit opcode set. Code lives in
addresses 0x00-0x3F, data in 0x40-0xFF. A basic block starts at a
program counter and ends at (including) the first branch, jump,
or halt instruction.

TODO: implement Guest and block decoding.
"""

OP_ADD = 1    # r[a] = r[a] + r[b]
OP_LOAD = 2   # r[a] = mem[b]
OP_STORE = 3  # mem[a] = r[b]
OP_SUB = 4    # r[a] = r[a] - r[b]
OP_JMP = 5    # pc = a
OP_JZ = 6     # if r[a] == 0: pc = b
OP_HALT = 7   # stop

_BRANCH_OPS = {OP_JMP, OP_JZ, OP_HALT}


class Guest:
    """Toy guest machine. TODO: implement."""

    def __init__(self):
        self.mem = [0] * 256
