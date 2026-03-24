"""Parse Strategy DSL from JSON."""

import json
from pathlib import Path
from typing import Union

from pydantic import ValidationError

from .types import Strategy


class ParseError(Exception):
    """Raised when strategy parsing fails."""

    def __init__(self, message: str, details: str | None = None):
        self.message = message
        self.details = details
        super().__init__(message)


def parse_strategy(source: Union[str, dict]) -> Strategy:
    """
    Parse a strategy from JSON string or dict.

    Args:
        source: JSON string or dict containing strategy definition

    Returns:
        Validated Strategy object

    Raises:
        ParseError: If parsing or validation fails
    """
    # Convert JSON string to dict if needed
    if isinstance(source, str):
        try:
            data = json.loads(source)
        except json.JSONDecodeError as e:
            raise ParseError(f"Invalid JSON: {e.msg}", details=str(e))
    else:
        data = source

    # Validate against Pydantic model
    try:
        return Strategy.model_validate(data)
    except ValidationError as e:
        raise ParseError("Strategy validation failed", details=str(e))


def parse_strategy_file(path: Union[str, Path]) -> Strategy:
    """
    Parse a strategy from a JSON file.

    Args:
        path: Path to JSON file

    Returns:
        Validated Strategy object

    Raises:
        ParseError: If file reading, parsing, or validation fails
    """
    path = Path(path)

    try:
        content = path.read_text()
    except FileNotFoundError:
        raise ParseError(f"Strategy file not found: {path}")
    except IOError as e:
        raise ParseError(f"Error reading file: {path}", details=str(e))

    return parse_strategy(content)
