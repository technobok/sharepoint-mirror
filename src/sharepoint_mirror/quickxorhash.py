"""Pure Python implementation of Microsoft's QuickXorHash algorithm.

QuickXorHash is a non-cryptographic hash used by OneDrive/SharePoint to verify
file integrity. It produces a 160-bit hash encoded as base64 for comparison
with the Graph API ``file.hashes.quickXorHash`` value.

Reference: Microsoft C# implementation in the OneDrive SDK.
"""

import base64
import struct

WIDTH_IN_BITS = 160
SHIFT = 11
NUM_CELLS = (WIDTH_IN_BITS - 1) // 64 + 1  # 3
BITS_IN_LAST_CELL = WIDTH_IN_BITS % 64  # 32
HASH_SIZE = WIDTH_IN_BITS // 8  # 20 bytes


class QuickXorHash:
    """Hashlib-style interface for QuickXorHash."""

    def __init__(self) -> None:
        self._data: list[int] = [0] * NUM_CELLS
        self._length_so_far: int = 0
        self._shift_so_far: int = 0

    def update(self, data: bytes | bytearray | memoryview) -> None:
        """Feed data into the hash."""
        current_shift = self._shift_so_far

        for byte in data:
            index = current_shift // 64
            offset = current_shift % 64

            self._data[index] ^= byte << offset

            # The last cell is only 32 bits wide, so its overflow threshold
            # is 24 (32-8), not 56 (64-8) like the full-width cells.
            is_last_cell = index == NUM_CELLS - 1
            bits_in_cell = BITS_IN_LAST_CELL if is_last_cell else 64
            if offset > bits_in_cell - 8:
                self._data[(index + 1) % NUM_CELLS] ^= byte >> (bits_in_cell - offset)

            current_shift = (current_shift + SHIFT) % WIDTH_IN_BITS

        self._shift_so_far = current_shift
        self._length_so_far += len(data)

    def digest(self) -> bytes:
        """Return the 20-byte hash value."""
        result = bytearray(HASH_SIZE)

        # Pack first two full 64-bit cells
        for i in range(NUM_CELLS - 1):
            struct.pack_into("<Q", result, i * 8, self._data[i] & 0xFFFFFFFFFFFFFFFF)

        # Last cell: only BITS_IN_LAST_CELL/8 = 4 bytes
        struct.pack_into(
            "<I",
            result,
            (NUM_CELLS - 1) * 8,
            self._data[NUM_CELLS - 1] & 0xFFFFFFFF,
        )

        # XOR the file length (8 bytes LE) into the last 8 bytes of the hash
        length_bytes = struct.pack("<Q", self._length_so_far & 0xFFFFFFFFFFFFFFFF)
        offset = HASH_SIZE - len(length_bytes)  # 20 - 8 = 12
        for i in range(len(length_bytes)):
            result[offset + i] ^= length_bytes[i]

        return bytes(result)

    def hexdigest(self) -> str:
        """Return the hash as a hex string."""
        return self.digest().hex()

    def base64digest(self) -> str:
        """Return the hash as a base64 string (matches Graph API format)."""
        return base64.b64encode(self.digest()).decode("ascii")


def quickxorhash(data: bytes) -> str:
    """Compute QuickXorHash of *data* and return base64-encoded string."""
    h = QuickXorHash()
    h.update(data)
    return h.base64digest()
