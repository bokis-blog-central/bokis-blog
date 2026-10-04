"""Generate a 256-bit key for the application's SECRET_KEY setting."""
import secrets


if __name__ == "__main__":
    print(secrets.token_hex(32))
