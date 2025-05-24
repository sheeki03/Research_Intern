import bcrypt
import yaml
from pathlib import Path
from src.config import USERS_CONFIG_PATH, DEFAULT_PROMPTS

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def init_users():
    """Initialize the users configuration file with default users."""
    # Create config directory if it doesn't exist
    Path(USERS_CONFIG_PATH).parent.mkdir(parents=True, exist_ok=True)
    
    # Initialize users with hashed passwords
    users = {
        "admin": {
            "password": hash_password("admin123"),
            "role": "admin",
            "system_prompt": DEFAULT_PROMPTS["admin"],
            "rate_limit": 100  # requests per hour
        },
        "researcher": {
            "password": hash_password("researcher123"),
            "role": "researcher",
            "system_prompt": DEFAULT_PROMPTS["researcher"],
            "rate_limit": 50  # requests per hour
        }
    }
    
    # Write users to config file
    with open(USERS_CONFIG_PATH, "w") as f:
        yaml.dump(users, f, default_flow_style=False)
    
    print("WARNING: Default users initialized. Please change passwords in production.")

if __name__ == "__main__":
    init_users() 