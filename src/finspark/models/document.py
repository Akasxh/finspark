"""Document models for uploaded BRDs, SOWs, API specs."""

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from finspark.models.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class Document(Base, UUIDMixin, TenantMixin, TimestampMixin):
    """Uploaded document (BRD, SOW, API spec)."""

    __tablename__ = "documents"

    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)  # docx, pdf, yaml, json
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    doc_type: Mapped[str] = mapped_column(String(50), nullable=False)  # brd, sow, api_spec, other
    status: Mapped[str] = mapped_column(
        String(20), default="uploaded"
    )  # uploaded, parsing, parsed, failed
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_result: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON - structured extraction
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
