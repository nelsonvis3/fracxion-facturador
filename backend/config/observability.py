"""Structured diagnostic metadata without request bodies, credentials or exception text."""

import json
import logging
import re
import traceback
import uuid
from datetime import UTC, datetime


class RequestIDMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = str(uuid.uuid4())
        response = self.get_response(request)
        response["X-Request-ID"] = request.request_id
        return response


class SafeJSONFormatter(logging.Formatter):
    def format(self, record):
        # A logging format string identifies the event. Interpolation arguments and
        # exception messages can contain SMTP credentials, tokens or request input.
        event = record.msg[:512] if isinstance(record.msg, str) else "application_event"
        result = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": event,
        }
        for key in ["request_id", "tenant_id", "job_id"]:
            value = str(getattr(record, key, ""))
            if key == "request_id" and not value:
                value = str(getattr(getattr(record, "request", None), "request_id", ""))
            if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", value):
                result[key] = value
        status = getattr(record, "status_code", None)
        if isinstance(status, int) and 100 <= status <= 599:
            result["status_code"] = status
        if record.exc_info and record.exc_info[0]:
            result["exception_type"] = record.exc_info[0].__name__
            result["frames"] = [
                {
                    "file": frame.filename.rsplit("/", 1)[-1],
                    "line": frame.lineno,
                    "function": frame.name,
                }
                for frame in traceback.extract_tb(record.exc_info[2])[-12:]
            ]
        return json.dumps(result, ensure_ascii=True)
