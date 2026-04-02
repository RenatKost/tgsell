"""Add auctions system: auctions + auction_bids tables, channel listing_type fields

Revision ID: 0012
Revises: 0011
"""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Note: enum types 'listingtype' and 'auctionstatus' are auto-created by SQLAlchemy
    # metadata when models are imported (env.py). We only need to add columns and tables.

    # --- Add auction fields to channels ---
    op.add_column("channels", sa.Column("listing_type", sa.String(20), server_default="sale", nullable=False))
    op.add_column("channels", sa.Column("auction_start_price", sa.Float(), nullable=True))
    op.add_column("channels", sa.Column("auction_bid_step", sa.Float(), nullable=True))
    op.add_column("channels", sa.Column("auction_duration_hours", sa.Integer(), nullable=True))

    # --- Auctions table ---
    op.create_table(
        "auctions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seller_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("start_price", sa.Float(), nullable=False),
        sa.Column("bid_step", sa.Float(), nullable=False, server_default="10"),
        sa.Column("current_price", sa.Float(), nullable=False),
        sa.Column("buyout_price", sa.Float(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="scheduled"),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
        sa.Column("winner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("bid_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # --- Auction bids table ---
    op.create_table(
        "auction_bids",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("auction_id", sa.Integer(), sa.ForeignKey("auctions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bidder_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("auction_bids")
    op.drop_table("auctions")
    op.drop_column("channels", "auction_duration_hours")
    op.drop_column("channels", "auction_bid_step")
    op.drop_column("channels", "auction_start_price")
    op.drop_column("channels", "listing_type")
    op.execute("DROP TYPE IF EXISTS auctionstatus")
    op.execute("DROP TYPE IF EXISTS listingtype")
