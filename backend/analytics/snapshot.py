from contextlib import contextmanager

from django.db import connection, transaction


@contextmanager
def reporting_snapshot():
    """One coherent PostgreSQL snapshot for a multi-query financial report."""
    outer_transaction = connection.in_atomic_block
    with transaction.atomic():
        if not outer_transaction:
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        yield
