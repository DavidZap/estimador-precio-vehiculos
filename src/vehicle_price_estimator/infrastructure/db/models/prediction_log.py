import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from vehicle_price_estimator.infrastructure.db.base import Base


class PredictionLogModel(Base):
    __tablename__ = "prediction_logs"
    __table_args__ = {"schema": "ops"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_registry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ml.model_registry.id"),
        nullable=True,
    )
    model_scope_requested: Mapped[str] = mapped_column(String(50), nullable=False)
    model_scope_used: Mapped[str] = mapped_column(String(50), nullable=False)
    request_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    response_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    predicted_price_cop: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
