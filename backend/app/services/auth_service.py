from __future__ import annotations

import re
import secrets

from backend.app.domain.account import AuthSession, PhysicianAccount
from backend.app.repositories.base import ArenaRepository


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


class AuthService:
    """Minimal prototype authentication with explicitly plaintext passwords."""

    def __init__(self, repository: ArenaRepository) -> None:
        self.repository = repository

    def register(self, username: str, password: str) -> tuple[PhysicianAccount, AuthSession]:
        normalized = self._normalize_username(username)
        if len(password) < 4:
            raise ValueError("Password must contain at least 4 characters")
        if len(password) > 128:
            raise ValueError("Password is too long")
        if self.repository.get_account(normalized):
            raise ValueError("Account already exists")
        account = PhysicianAccount(
            username=normalized,
            password_plaintext=password,
        )
        self.repository.add_account(account)
        return account, self._issue_session(normalized)

    def login(self, username: str, password: str) -> tuple[PhysicianAccount, AuthSession]:
        normalized = self._normalize_username(username)
        account = self.repository.get_account(normalized)
        if account is None or not secrets.compare_digest(
            account.password_plaintext, password
        ):
            raise ValueError("Invalid account or password")
        return account, self._issue_session(normalized)

    def account_for_token(self, token: str) -> PhysicianAccount:
        session = self.repository.get_auth_session(token)
        if session is None:
            raise ValueError("Authentication required")
        account = self.repository.get_account(session.username)
        if account is None:
            raise ValueError("Authentication required")
        return account

    def logout(self, token: str) -> None:
        self.repository.delete_auth_session(token)

    def _issue_session(self, username: str) -> AuthSession:
        session = AuthSession(
            token=secrets.token_urlsafe(32),
            username=username,
        )
        self.repository.add_auth_session(session)
        return session

    @staticmethod
    def _normalize_username(username: str) -> str:
        normalized = username.strip().lower()
        if not 3 <= len(normalized) <= 64 or not USERNAME_PATTERN.fullmatch(normalized):
            raise ValueError(
                "Account must be 3-64 letters, numbers, underscores, or hyphens"
            )
        return normalized
