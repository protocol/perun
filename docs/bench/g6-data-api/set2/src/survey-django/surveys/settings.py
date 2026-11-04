import os

SECRET_KEY = os.environ["SURVEYS_SECRET_KEY"]
DEBUG = False
ALLOWED_HOSTS = ["surveys.example.com"]
ROOT_URLCONF = "surveys.urls"
INSTALLED_APPS = ["django.contrib.sessions"]
MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "surveys.access.TokenMiddleware",
]
SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 3600
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_TRUSTED_ORIGINS = ["https://surveys.example.com"]
DATABASES = {}
