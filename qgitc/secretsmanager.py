# -*- coding: utf-8 -*-

import base64


class SecretsManager:
    """Manages obfuscation and de-obfuscation of sensitive data."""

    # XOR key constant - used to obfuscate/de-obfuscate
    _XOR_KEY = 0x42  # Simple XOR byte key

    @classmethod
    def encode(cls, plaintext: str) -> str:
        """
        Encodes plaintext using base64 + XOR obfuscation.
        
        Args:
            plaintext: The string to encode
            
        Returns:
            Obfuscated encoded string
        """
        # First base64 encode
        b64 = base64.b64encode(plaintext.encode('utf-8')).decode('ascii')
        # Then XOR each byte for additional obfuscation
        xored = bytes(ord(c) ^ cls._XOR_KEY for c in b64)
        # Return as hex string
        return xored.hex()

    @classmethod
    def decode(cls, encodedHex: str) -> str:
        """
        Decodes hex-encoded obfuscated string.
        
        Args:
            encodedHex: The hex-encoded obfuscated string
            
        Returns:
            Decoded plaintext string
        """
        try:
            # Convert hex back to bytes
            xored = bytes.fromhex(encodedHex)
            # Reverse XOR
            b64Bytes = bytes(b ^ cls._XOR_KEY for b in xored)
            # Decode base64
            plaintext = base64.b64decode(b64Bytes).decode('utf-8')
            return plaintext
        except Exception as e:
            raise RuntimeError(f"Failed to decode secret: {e}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Usage: secretsmanager.py <encode|decode> <string>")
        sys.exit(1)

    action, value = sys.argv[1], sys.argv[2]
    if action == "encode":
        print(SecretsManager.encode(value))
    elif action == "decode":
        print(SecretsManager.decode(value))
    else:
        print(f"Invalid action: {action}")
        sys.exit(1)
