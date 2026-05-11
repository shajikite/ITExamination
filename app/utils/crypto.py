import base64
import hashlib
from cryptography.fernet import Fernet
from flask import current_app

def get_fernet():
    """
    Derives a 32-byte url-safe base64-encoded key from the Flask SECRET_KEY
    and returns a Fernet instance for encryption/decryption.
    """
    secret_key = current_app.config.get('SECRET_KEY', 'default-dev-key').encode()
    # Hash the secret key to ensure it's exactly 32 bytes, then base64 encode it
    key = base64.urlsafe_b64encode(hashlib.sha256(secret_key).digest())
    return Fernet(key)

def encrypt_data(data: bytes) -> bytes:
    """Encrypts binary data using Fernet."""
    if not data:
        return None
    f = get_fernet()
    return f.encrypt(data)

def decrypt_data(encrypted_data: bytes) -> bytes:
    """Decrypts binary data using Fernet."""
    if not encrypted_data:
        return None
    f = get_fernet()
    return f.decrypt(encrypted_data)
