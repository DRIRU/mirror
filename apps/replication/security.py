"""
Cryptographic and Security Utilities for Mirror Trade Replication.
Provides field-level encryption at rest, credential masking, format validation, and audit safeguards.
"""

import base64
import hashlib
import re
from typing import Tuple, List, Dict, Any, Optional
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

ENCRYPTION_PREFIX = "enc:v1:"


def get_encryption_key() -> bytes:
    """
    Retrieves the 32-byte Fernet key from settings or derives it deterministically from SECRET_KEY.
    Ensures zero unencrypted secrets at rest.
    """
    custom_key = getattr(settings, "MIRROR_ENCRYPTION_KEY", None)
    if custom_key:
        try:
            if isinstance(custom_key, str):
                custom_key = custom_key.strip().encode("utf-8")
            decoded = base64.urlsafe_b64decode(custom_key)
            if len(decoded) == 32:
                return custom_key
        except Exception:
            pass

    # Deterministic fallback derived from Django SECRET_KEY via SHA-256
    secret_bytes = settings.SECRET_KEY.encode("utf-8")
    digest = hashlib.sha256(secret_bytes).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_secret(raw_secret: str) -> str:
    """
    Encrypts a raw API secret string using authenticated AES-128/Fernet.
    Returns string prefixed with 'enc:v1:' for format versioning.
    Idempotent: If already encrypted, returns as-is.
    """
    if not raw_secret:
        return ""
    raw_secret = raw_secret.strip()
    if raw_secret.startswith(ENCRYPTION_PREFIX):
        return raw_secret

    key = get_encryption_key()
    fernet = Fernet(key)
    ciphertext = fernet.encrypt(raw_secret.encode("utf-8")).decode("utf-8")
    return f"{ENCRYPTION_PREFIX}{ciphertext}"


def decrypt_secret(stored_secret: str) -> str:
    """
    Decrypts an encrypted API secret.
    If the secret does not have the 'enc:v1:' prefix, assumes legacy unencrypted value and returns it.
    Safely handles invalid tokens or corruption without crashing.
    """
    if not stored_secret:
        return ""
    stored_secret = stored_secret.strip()
    if not stored_secret.startswith(ENCRYPTION_PREFIX):
        return stored_secret

    token = stored_secret[len(ENCRYPTION_PREFIX):]
    try:
        key = get_encryption_key()
        fernet = Fernet(key)
        return fernet.decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception):
        return "[SECURE_DECRYPTION_ERROR]"


def mask_api_key(api_key: str) -> str:
    """
    Safely masks an API key for UI rendering.
    e.g., '7506788c...b8fd' -> '750678••••••••b8fd'
    """
    if not api_key:
        return ""
    key = api_key.strip()
    if len(key) <= 8:
        return "••••" + key[-2:]
    return f"{key[:6]}••••••••{key[-4:]}"


def mask_api_secret(secret_text: str) -> str:
    """
    Safely masks an API secret for UI rendering.
    Always returns masked string, never exposing more than the last 4 characters.
    """
    if not secret_text:
        return "••••••••••••••••"
    decrypted = decrypt_secret(secret_text)
    if not decrypted or decrypted == "[SECURE_DECRYPTION_ERROR]":
        return "••••••••••••••••"
    if len(decrypted) <= 4:
        return "••••••••"
    return f"••••••••••••••••{decrypted[-4:]}"


def inspect_secret_format(secret: str) -> Dict[str, Any]:
    """
    Inspects key/secret syntax and returns diagnostics without leaking credentials.
    """
    if not secret:
        return {"valid": False, "type": "Empty", "description": "No secret provided"}
    
    clean = secret.strip()
    length = len(clean)

    # Check if 64-char Hex (standard for Ed25519 secret keys like CoinSwitch PRO / DMA)
    if length == 64 and re.fullmatch(r"[0-9a-fA-F]{64}", clean):
        return {
            "valid": True,
            "type": "Ed25519 Hex",
            "length": 64,
            "description": "256-bit Hexadecimal Ed25519 Secret Key detected",
            "strength": "High",
        }

    # Check if Base64 or standard alphanumeric token
    if length >= 32 and re.fullmatch(r"[A-Za-z0-9+/=_-]+", clean):
        return {
            "valid": True,
            "type": "Base64 / Alphanumeric",
            "length": length,
            "description": f"{length}-character Base64/API Token detected",
            "strength": "Medium" if length < 40 else "High",
        }

    if length >= 16:
        return {
            "valid": True,
            "type": "Standard API Secret",
            "length": length,
            "description": f"{length}-character API Secret detected",
            "strength": "Medium",
        }

    return {
        "valid": False,
        "type": "Weak",
        "length": length,
        "description": f"Secret is too short ({length} chars, minimum 16 required)",
        "strength": "Low",
    }


def validate_follower_input(
    name: str,
    api_key: str,
    api_secret: str,
    is_edit: bool = False,
) -> List[str]:
    """
    Validates form input against strict security standards.
    """
    errors = []
    if not name or len(name.strip()) < 2:
        errors.append("Account / Friend Name must be at least 2 characters.")

    if not api_key or len(api_key.strip()) < 8:
        errors.append("API Key must be at least 8 characters.")

    if not is_edit or (is_edit and api_secret.strip()):
        if not api_secret or len(api_secret.strip()) < 16:
            errors.append("API Secret must be at least 16 characters.")

    # Check for placeholder strings
    lowered_key = (api_key or "").lower()
    lowered_secret = (api_secret or "").lower()
    if any(p in lowered_key for p in ["your_api_key", "my_api_key"]):
        errors.append("API Key appears to be a placeholder.")
    if any(p in lowered_secret for p in ["your_secret", "my_secret", "secret_here"]):
        errors.append("API Secret appears to be a placeholder.")

    return errors
