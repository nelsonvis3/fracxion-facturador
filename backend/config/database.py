"""PostgreSQL URL parsing without exposing credentials in configuration errors."""

from urllib.parse import parse_qs, unquote, urlsplit

from django.core.exceptions import ImproperlyConfigured


def database_from_url(value):
    try:
        url = urlsplit(value)
        query = parse_qs(url.query, strict_parsing=True)
        if (
            url.scheme not in {"postgres", "postgresql"}
            or not url.hostname
            or not url.username
            or not url.password
            or not url.path.removeprefix("/")
            or url.fragment
            or set(query) - {"sslmode", "channel_binding"}
            or any(len(values) != 1 for values in query.values())
        ):
            raise ValueError()
        options = {key: values[0] for key, values in query.items()}
        options.setdefault("sslmode", "require")
        if options["sslmode"] not in {"require", "verify-ca", "verify-full"}:
            raise ValueError()
        if options.get("channel_binding", "prefer") not in {"disable", "prefer", "require"}:
            raise ValueError()
        options["connect_timeout"] = 10
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": unquote(url.path[1:]),
            "USER": unquote(url.username),
            "PASSWORD": unquote(url.password),
            "HOST": url.hostname,
            "PORT": url.port or 5432,
            "CONN_MAX_AGE": 0,
            "CONN_HEALTH_CHECKS": True,
            "DISABLE_SERVER_SIDE_CURSORS": True,
            "OPTIONS": options,
        }
    except (ValueError, TypeError):
        raise ImproperlyConfigured(
            "DATABASE_URL debe ser una URL PostgreSQL válida con TLS."
        ) from None
