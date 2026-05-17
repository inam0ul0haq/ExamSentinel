"""
In-memory session / state holder for the running client.

Stores:
- Currently authenticated user profile and JWT.
- Transient navigation state (e.g. selected course, selected exam).
- Observer callbacks that fire on logout so screens can react.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, List, Optional


class SessionState:
    """Singleton-style session store — instantiated once in ``main.py``."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._token: Optional[str] = None
        self._user: Optional[Dict[str, Any]] = None
        self._transient: Dict[str, Any] = {}
        self._logout_observers: List[Callable[[], None]] = []

    # -- authentication state -----------------------------------------------

    @property
    def token(self) -> Optional[str]:
        with self._lock:
            return self._token

    @property
    def user(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._user.copy() if self._user else None

    @property
    def is_authenticated(self) -> bool:
        with self._lock:
            return self._token is not None

    def login(self, token: str, user: Dict[str, Any]) -> None:
        """Store JWT and user profile after successful authentication."""
        with self._lock:
            self._token = token
            self._user = dict(user)

    def logout(self) -> None:
        """Clear auth state and notify observers."""
        with self._lock:
            self._token = None
            self._user = None
            self._transient.clear()
            observers = list(self._logout_observers)
        for cb in observers:
            cb()

    # -- logout observers ---------------------------------------------------

    def on_logout(self, callback: Callable[[], None]) -> None:
        """Register a callback that fires when ``logout()`` is called."""
        with self._lock:
            self._logout_observers.append(callback)

    def remove_logout_observer(self, callback: Callable[[], None]) -> None:
        with self._lock:
            try:
                self._logout_observers.remove(callback)
            except ValueError:
                pass

    # -- transient navigation state -----------------------------------------

    def set(self, key: str, value: Any) -> None:
        """Stash an arbitrary value for cross-screen navigation."""
        with self._lock:
            self._transient[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._transient.get(key, default)

    def pop(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._transient.pop(key, default)
