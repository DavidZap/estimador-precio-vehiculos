from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from vehicle_price_estimator.infrastructure.db.base import Base


class ColombiaLocationReferenceModel(Base):
    __tablename__ = "colombia_location_reference"
    __table_args__ = (
        UniqueConstraint("municipality_code"),
        UniqueConstraint("department_name_std", "city_name_std"),
        {"schema": "ref"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    department_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    department_name: Mapped[str] = mapped_column(String(120), nullable=False)
    department_name_std: Mapped[str] = mapped_column(String(120), nullable=False)
    municipality_code: Mapped[str] = mapped_column(String(10), nullable=False)
    city_name: Mapped[str] = mapped_column(String(120), nullable=False)
    city_name_std: Mapped[str] = mapped_column(String(120), nullable=False)
    municipality_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(12, 8), nullable=True)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(12, 8), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
