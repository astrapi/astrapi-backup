import os
from dotenv import load_dotenv

# .env nur einmal laden
load_dotenv("config/secrets.env")

def get_secret(key: str) -> str: 
    value = os.getenv(key) 
    if not value: 
        raise RuntimeError(f"Secret '{key}' ist nicht gesetzt!") 
    return value