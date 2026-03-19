import os
from datetime import timedelta


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DEFAULT_SQLITE_PATH = os.path.join(BASE_DIR, "instance", "mebelgrad_kis.db")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "mebelgrad-dev-secret")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "mebelgrad-jwt-secret")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{DEFAULT_SQLITE_PATH}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    REMEMBER_COOKIE_DURATION = timedelta(days=7)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
    ITEMS_PER_PAGE = 20


class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False


class TestingConfig(Config):
    TESTING = True
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


class ProductionConfig(Config):
    DEBUG = False
    TESTING = False


config = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
