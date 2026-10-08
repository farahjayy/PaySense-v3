"""Deterministic randomness for the generator.

Each profile gets its own stream, and within a profile each *component* (income, bills, spending,
...) gets its own named stream. Streams are derived from `(master_seed, profile index, name)`, so:
  * profile N is identical whether 10 or 10,000 profiles are generated (a 10-run is a prefix of
    a 100-run), and
  * changing how many numbers one component draws never shifts any other component's numbers.
"""

import zlib

import numpy as np


def profile_rng(master_seed: int, index: int, stream: str) -> np.random.Generator:
    if master_seed < 0 or index < 0:
        raise ValueError("master_seed and index must be non-negative")
    name = zlib.crc32(stream.encode("utf-8"))  # stable across runs, unlike hash()
    sequence = np.random.SeedSequence(entropy=master_seed, spawn_key=(index, name))
    return np.random.Generator(np.random.PCG64(sequence))
