"""Global determinism and seed management (R6)."""

import os
import random


def set_global_seed(seed: int = 42) -> None:
    """Set global random seed across Python runtime, random, numpy, and torch if installed.

    Guarantees deterministic splits and pipeline repeatability per R6.
    """
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)

    # Optional / lazy packages
    try:
        import numpy as np

        np.random.seed(seed)
    except ImportError:
        pass

    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except ImportError:
        pass
