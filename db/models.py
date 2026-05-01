from datetime import datetime, timezone
from sqlalchemy import Integer, String, DateTime, Float
from sqlalchemy.orm import Mapped, mapped_column
from db.database import Base


class UpscaledImage(Base):
    __tablename__ = "runpod_worker_upscaled_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str | None] = mapped_column(String, nullable=True)
    processing_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    original_url: Mapped[str] = mapped_column(String, nullable=False)
    output_url: Mapped[str] = mapped_column(String, nullable=False)
    scale: Mapped[int] = mapped_column(Integer, nullable=False)
    original_width: Mapped[int] = mapped_column(Integer, nullable=False)
    original_height: Mapped[int] = mapped_column(Integer, nullable=False)
    output_width: Mapped[int] = mapped_column(Integer, nullable=False)
    output_height: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
