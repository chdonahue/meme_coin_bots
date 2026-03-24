"""Business rule validation for Strategy DSL."""

from .types import (
    Strategy,
    Condition,
    SimpleCondition,
    AllCondition,
    AnyCondition,
    NotCondition,
)

# Known built-in metrics (not derived streams)
BUILTIN_METRICS = {
    "price",
    "price_change_pct",
    "volume",
    "volume_change_pct",
    "position_gain_pct",
    "position_size",
}


def validate_strategy(strategy: Strategy) -> list[str]:
    """
    Validate business rules for a strategy.

    Args:
        strategy: Parsed Strategy object

    Returns:
        List of validation error messages (empty if valid)
    """
    errors: list[str] = []

    # Collect valid identifiers
    valid_tokens = set(strategy.tokens)
    derived_stream_ids = {ds.id for ds in strategy.derived_streams}

    # Validate derived streams reference valid tokens
    for ds in strategy.derived_streams:
        if ds.token not in valid_tokens:
            errors.append(f"Derived stream '{ds.id}' references unknown token: {ds.token}")

    # Check for duplicate derived stream IDs
    seen_ds_ids: set[str] = set()
    for ds in strategy.derived_streams:
        if ds.id in seen_ds_ids:
            errors.append(f"Duplicate derived stream ID: {ds.id}")
        seen_ds_ids.add(ds.id)

    # Check for duplicate trigger IDs
    seen_trigger_ids: set[str] = set()
    for trigger in strategy.triggers:
        if trigger.id in seen_trigger_ids:
            errors.append(f"Duplicate trigger ID: {trigger.id}")
        seen_trigger_ids.add(trigger.id)

    # Validate triggers
    for trigger in strategy.triggers:
        errors.extend(
            _validate_condition(
                trigger.when,
                valid_tokens,
                derived_stream_ids,
                f"trigger '{trigger.id}'",
            )
        )

        # Validate action references valid token
        if trigger.action.token not in valid_tokens:
            errors.append(
                f"Trigger '{trigger.id}' action references unknown token: {trigger.action.token}"
            )

    # Validate risk rules bounds
    rr = strategy.risk_rules
    if rr.stop_loss_pct < -100 or rr.stop_loss_pct > 0:
        errors.append(f"stop_loss_pct must be between -100 and 0, got: {rr.stop_loss_pct}")
    if rr.max_position_pct <= 0 or rr.max_position_pct > 100:
        errors.append(f"max_position_pct must be between 0 and 100, got: {rr.max_position_pct}")
    if rr.max_trades_per_day <= 0:
        errors.append(f"max_trades_per_day must be positive, got: {rr.max_trades_per_day}")
    if rr.slippage_limit_bps < 0 or rr.slippage_limit_bps > 10000:
        errors.append(
            f"slippage_limit_bps must be between 0 and 10000, got: {rr.slippage_limit_bps}"
        )

    return errors


def _validate_condition(
    condition: Condition,
    valid_tokens: set[str],
    derived_stream_ids: set[str],
    context: str,
) -> list[str]:
    """Recursively validate a condition."""
    errors: list[str] = []

    if isinstance(condition, SimpleCondition):
        # Check if metric is builtin, derived, or invalid
        metric = condition.metric
        if metric not in BUILTIN_METRICS and metric not in derived_stream_ids:
            # Might be a builtin metric that requires a token
            if condition.token is None and metric in BUILTIN_METRICS:
                pass  # OK, some metrics don't need token
            elif condition.token is None:
                errors.append(
                    f"In {context}: metric '{metric}' is not a known builtin or derived stream"
                )

        # Check token reference if present
        if condition.token is not None and condition.token not in valid_tokens:
            errors.append(f"In {context}: condition references unknown token: {condition.token}")

        # Check compare_to reference if present
        if condition.compare_to is not None:
            if (
                condition.compare_to not in BUILTIN_METRICS
                and condition.compare_to not in derived_stream_ids
            ):
                errors.append(
                    f"In {context}: compare_to references unknown metric: {condition.compare_to}"
                )

    elif isinstance(condition, AllCondition):
        for sub in condition.all:
            errors.extend(_validate_condition(sub, valid_tokens, derived_stream_ids, context))

    elif isinstance(condition, AnyCondition):
        for sub in condition.any:
            errors.extend(_validate_condition(sub, valid_tokens, derived_stream_ids, context))

    elif isinstance(condition, NotCondition):
        errors.extend(
            _validate_condition(condition.not_, valid_tokens, derived_stream_ids, context)
        )

    return errors
