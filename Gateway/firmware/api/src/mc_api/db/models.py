"""api.db tables (Gateway/specs.md 4.1). Timestamps are UTC Unix seconds."""
from sqlalchemy import ForeignKey, Index, Integer, String, JSON, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[dict | list | str | int | bool | None] = mapped_column(JSON, nullable=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True)
    password_hash: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    display_name: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[int] = mapped_column(Integer)
    disabled_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    __table_args__ = (Index("uq_users_owner", "role", unique=True, sqlite_where=text("role = 'owner'")),)


class Token(Base):
    __tablename__ = "tokens"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[int] = mapped_column(Integer)
    last_used_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revoked_at: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Invite(Base):
    __tablename__ = "invites"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    code_hash: Mapped[str] = mapped_column(String, unique=True)
    role: Mapped[str] = mapped_column(String)
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[int] = mapped_column(Integer)
    used_by: Mapped[str | None] = mapped_column(String, nullable=True)
    used_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revoked_at: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ts: Mapped[int] = mapped_column(Integer, index=True)
    ip: Mapped[str | None] = mapped_column(String, nullable=True)
