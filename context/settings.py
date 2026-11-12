"""Settings come from the environment (.env is loaded if present). Defaults = local docker stand."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path):
    # shortcut: tiny .env reader instead of a dependency; upgrade to django-environ if values need quoting
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_dotenv(BASE_DIR / ".env")
env = os.environ.get

SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-only-not-secret")
DEBUG = env("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "rest_framework", "catalog", "ctx", "evals", "lab", "optimizer",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]
ROOT_URLCONF = "context.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
DATABASES = {"default": {
    "ENGINE": "django.db.backends.mysql",
    "HOST": env("DB_HOST", "127.0.0.1"), "PORT": env("DB_PORT", "3307"),
    "NAME": env("DB_NAME", "ctxc"), "USER": env("DB_USER", "ctxc"), "PASSWORD": env("DB_PASSWORD", "ctxc-local"),
    "OPTIONS": {"charset": "utf8mb4"},
    "TEST": {"CHARSET": "utf8mb4", "COLLATION": "utf8mb4_unicode_ci"},
}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

REST_FRAMEWORK = {"DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination", "PAGE_SIZE": 20}

CELERY_BROKER_URL = env("CELERY_BROKER_URL", "amqp://guest:guest@127.0.0.1:5673//")
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_ALWAYS_EAGER = env("CELERY_TASK_ALWAYS_EAGER", "0") == "1"

ES_URL = env("ES_URL", "http://127.0.0.1:9200")
NEO4J_URL = env("NEO4J_URL", "bolt://127.0.0.1:7687")
NEO4J_AUTH = (env("NEO4J_USER", "neo4j"), env("NEO4J_PASSWORD", "ctxc-local-pass"))

CTXC_SCAN_BUDGET_PCT = int(env("CTXC_SCAN_BUDGET_PCT", "5"))
CTXC_LLM_BASE_URL = env("CTXC_LLM_BASE_URL", "")
CTXC_LLM_API_KEY = env("CTXC_LLM_API_KEY", "")
CTXC_LLM_MODEL = env("CTXC_LLM_MODEL", "")
CTXC_LLM_TIMEOUT = int(env("CTXC_LLM_TIMEOUT", "60"))
CTXC_LLM_NAME = env("CTXC_LLM_NAME", "openrouter")
CTXC_LLM2_BASE_URL = env("CTXC_LLM2_BASE_URL", "")  # optional backup provider (own limits), e.g. NVIDIA NIM
CTXC_LLM2_API_KEY = env("CTXC_LLM2_API_KEY", "")
CTXC_LLM2_MODEL = env("CTXC_LLM2_MODEL", "")
CTXC_LLM2_NAME = env("CTXC_LLM2_NAME", "nim")

LOGGING = {"version": 1, "disable_existing_loggers": False,
           "handlers": {"console": {"class": "logging.StreamHandler"}},
           "root": {"handlers": ["console"], "level": "INFO"},
           "loggers": {"httpx": {"level": "WARNING"}, "elastic_transport": {"level": "WARNING"},
                       "neo4j": {"level": "WARNING"}}}
ES_INDEX = env("ES_INDEX", "cards")  # alias; physical indices are <alias>_v<N>
CELERY_BEAT_SCHEDULE = {"scan-all-portals": {"task": "ctx.tasks.scan_all", "schedule": 3600.0}}
# "prod" or "preprod". Preprod has its own MariaDB database and ES alias; it shares the Neo4j server read-only
# (graph writes are refused) and is the only place where AutoContext Lab may write candidate cards.
CTXC_ENV = env("CTXC_ENV", "prod")
