"""Shared rate limiter instance. Kept in its own module so both main.py
(which registers it on the app) and routes.py (which applies it to
endpoints) can import it without a circular dependency."""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
