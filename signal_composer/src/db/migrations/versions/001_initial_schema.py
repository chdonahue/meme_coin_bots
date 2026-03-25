"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-03-25

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create users table first (no dependencies)
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("wallet_address", sa.String(64), nullable=False),
        sa.Column("username", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_wallet_address", "users", ["wallet_address"], unique=True)
    op.create_unique_constraint("uq_users_username", "users", ["username"])

    # Create strategies table (depends on users)
    op.create_table(
        "strategies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("external_id", sa.String(50), nullable=False),
        sa.Column("creator_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=False, server_default=""),
        sa.Column("dsl_json", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_strategies_external_id", "strategies", ["external_id"], unique=True)

    # Create strategy_performance table (depends on strategies)
    op.create_table(
        "strategy_performance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("strategy_id", sa.Integer(), sa.ForeignKey("strategies.id"), nullable=False),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_return_pct", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("sharpe_ratio", sa.Float(), nullable=True),
        sa.Column("max_drawdown_pct", sa.Float(), nullable=True),
        sa.Column("trade_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("win_rate", sa.Float(), nullable=True),
    )
    op.create_index("ix_strategy_performance_strategy_id", "strategy_performance", ["strategy_id"])
    op.create_index("ix_strategy_performance_date", "strategy_performance", ["date"])
    op.create_index(
        "ix_perf_strategy_date", "strategy_performance", ["strategy_id", "date"], unique=True
    )

    # Create paper_trades table (depends on strategies)
    op.create_table(
        "paper_trades",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("strategy_id", sa.Integer(), sa.ForeignKey("strategies.id"), nullable=False),
        sa.Column("trigger_id", sa.String(50), nullable=False),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("action", sa.String(10), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("price_at_exec", sa.Float(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_paper_trades_strategy_id", "paper_trades", ["strategy_id"])
    op.create_index("ix_paper_trades_timestamp", "paper_trades", ["timestamp"])

    # Create price_data table (no foreign key dependencies)
    op.create_table(
        "price_data",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=True),
        sa.Column("source", sa.String(20), nullable=False),
    )
    op.create_index("ix_price_data_token", "price_data", ["token"])
    op.create_index("ix_price_data_timestamp", "price_data", ["timestamp"])
    op.create_index("ix_price_token_time", "price_data", ["token", "timestamp"])

    # Create portfolios table (depends on users and strategies)
    op.create_table(
        "portfolios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("strategy_id", sa.Integer(), sa.ForeignKey("strategies.id"), nullable=False),
        sa.Column("shares_owned", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("entry_value", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("current_value", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_portfolios_user_id", "portfolios", ["user_id"])
    op.create_index("ix_portfolios_strategy_id", "portfolios", ["strategy_id"])
    op.create_index(
        "ix_portfolio_user_strategy", "portfolios", ["user_id", "strategy_id"], unique=True
    )


def downgrade() -> None:
    # Drop tables in reverse order (respect foreign key constraints)
    op.drop_table("portfolios")
    op.drop_table("price_data")
    op.drop_table("paper_trades")
    op.drop_table("strategy_performance")
    op.drop_table("strategies")
    op.drop_table("users")
