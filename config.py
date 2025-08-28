import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')
STATIC_DIR = os.path.join(BASE_DIR, 'static')

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

# Load .env if present
if os.path.exists(os.path.join(BASE_DIR, '.env')):
    load_dotenv(os.path.join(BASE_DIR, '.env'))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', f"sqlite:///{os.path.join(DATA_DIR, 'dailynews.db')}")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Scheduler settings
    SCHEDULER_API_ENABLED = True

    # News settings
    DEFAULT_UPDATE_INTERVAL_MINUTES = int(os.environ.get('DEFAULT_UPDATE_INTERVAL_MINUTES', '60'))

    # Gemini CLI
    GEMINI_CLI_CMD = os.environ.get('GEMINI_CLI_CMD', 'gemini')
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')

    # MyMemory API
    MYMEMORY_EMAIL = os.environ.get('MYMEMORY_EMAIL', '')

class DevConfig(Config):
    DEBUG = True

class ProdConfig(Config):
    DEBUG = False