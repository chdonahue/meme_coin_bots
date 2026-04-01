"""add live trading tables

Revision ID: 9be0511a48c6
Revises: 001
Create Date: 2026-03-31 22:03:45.452777

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9be0511a48c6"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create live_trading_sessions table
    op.create_table(
        "live_trading_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("strategy_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("wallet_address", sa.String(length=44), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="running"),
        # Safety config
        sa.Column(
            "max_trade_usd", sa.Numeric(precision=12, scale=2), nullable=False, server_default="500"
        ),
        sa.Column(
            "max_daily_usd",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="2000",
        ),
        sa.Column(
            "max_daily_loss_usd",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="500",
        ),
        # Circuit breaker
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("circuit_breaker_tripped_at", sa.DateTime(timezone=True), nullable=True),
        # Tracking
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_tick_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_reconciled_at", sa.DateTime(timezone=True), nullable=True),
        # Daily counters
        sa.Column(
            "daily_volume_usd",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "daily_pnl_usd", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0"
        ),
        sa.Column("daily_reset_date", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(
            ["strategy_id"],
            ["strategies.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_live_trading_sessions_strategy_id"),
        "live_trading_sessions",
        ["strategy_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_live_trading_sessions_user_id"), "live_trading_sessions", ["user_id"], unique=False
    )

    # Create live_transactions table
    op.create_table(
        "live_transactions",
        sa.Column("id", sa.String(length=36), nullable=False),  # UUID
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("trigger_id", sa.String(length=100), nullable=False),
        sa.Column("action_type", sa.String(length=20), nullable=False),
        sa.Column("token_address", sa.String(length=44), nullable=False),
        # State
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("state_history", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        # Quote data
        sa.Column("quote_input_mint", sa.String(length=44), nullable=True),
        sa.Column("quote_output_mint", sa.String(length=44), nullable=True),
        sa.Column("quote_amount_in", sa.BigInteger(), nullable=True),
        sa.Column("quote_expected_out", sa.BigInteger(), nullable=True),
        sa.Column("quote_price_impact_pct", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("quote_expires_at", sa.DateTime(timezone=True), nullable=True),
        # Execution
        sa.Column("tx_signature", sa.String(length=88), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_amount_out", sa.BigInteger(), nullable=True),
        sa.Column("actual_price", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("slippage_bps", sa.Integer(), nullable=True),
        sa.Column("fee_lamports", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["live_trading_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_live_transactions_session_id"), "live_transactions", ["session_id"], unique=False
    )
    op.create_index(
        op.f("ix_live_transactions_state"), "live_transactions", ["state"], unique=False
    )
    op.create_index(
        op.f("ix_live_transactions_tx_signature"),
        "live_transactions",
        ["tx_signature"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_live_transactions_tx_signature"), table_name="live_transactions")
    op.drop_index(op.f("ix_live_transactions_state"), table_name="live_transactions")
    op.drop_index(op.f("ix_live_transactions_session_id"), table_name="live_transactions")
    op.drop_table("live_transactions")
    op.drop_index(op.f("ix_live_trading_sessions_user_id"), table_name="live_trading_sessions")
    op.drop_index(op.f("ix_live_trading_sessions_strategy_id"), table_name="live_trading_sessions")
    op.drop_table("live_trading_sessions")
