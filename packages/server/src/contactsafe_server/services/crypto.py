from cryptography.fernet import Fernet, InvalidToken


class TokenEncryptor:
    def __init__(self, key: str) -> None:
        self._fernet: Fernet = Fernet(key.encode("utf-8"))

    def encrypt(self, plaintext: str) -> bytes:
        return self._fernet.encrypt(plaintext.encode("utf-8"))

    def decrypt(self, ciphertext: bytes) -> str:
        try:
            return self._fernet.decrypt(ciphertext).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Failed to decrypt token") from exc
