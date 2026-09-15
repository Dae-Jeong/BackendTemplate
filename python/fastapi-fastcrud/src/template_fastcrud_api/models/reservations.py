from sqlalchemy import JSON, CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ProductModel(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("available >= 0", name="ck_products_available_nonnegative"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    available: Mapped[int] = mapped_column(Integer, nullable=False)


class ReservationModel(Base):
    __tablename__ = "reservations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    product_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("products.id"), nullable=False
    )
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)


class IdempotencyKeyModel(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        CheckConstraint(
            "length(key) BETWEEN 1 AND 128", name="ck_idempotency_key_length"
        ),
    )

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    product_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("products.id"), nullable=False
    )
    reservation_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("reservations.id"), unique=True, nullable=False
    )
    response: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
