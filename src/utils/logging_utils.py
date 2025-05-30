"""
Logging utils
"""

import logging
import os
from datetime import datetime


def setup_logger(session_name="test", log_dir=None):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    # If no log_dir specified, use caller's directory
    if log_dir is None:
        import inspect

        caller_file = inspect.stack()[1].filename
        log_dir = os.path.join(os.path.dirname(caller_file), "logs")

    os.makedirs(log_dir, exist_ok=True)
    log_filename = f"{session_name}_{timestamp}.log"
    log_path = os.path.join(log_dir, log_filename)

    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Also print logs to console
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")
    console.setFormatter(formatter)
    logging.getLogger().addHandler(console)

    logging.info(f"Logger initialized")
