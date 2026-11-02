"""Reserve bounded user-triggered model operations before doing external work.

Counts operations, not tokens or currency. Actions analysis has separate trusted
workflow concurrency/timeouts and provider billing limits remain necessary.
"""
import hashlib
import time
from datetime import datetime, timezone

from sqlalchemy import delete, update

from docsync.web.models import UsageBucket


def reserve_usage(engine, actor, repo_id, *, scope, settings, now=None):
    if scope not in {'chat', 'model'}:
        raise ValueError('Unknown model allowance')
    daily = settings.chat_daily_limit if scope == 'chat' else settings.model_action_daily_limit
    if any(type(value) is not int or value < 1 or value > 10000 for value in (daily, settings.repository_daily_limit)):
        raise ValueError('Model operation limits must be integers between 1 and 10000')
    now = time.time() if now is None else now
    day = datetime.fromtimestamp(now, timezone.utc).strftime('%Y-%m-%d')
    minute = day + ':' + str(int(now // 60))
    if engine.dialect.name == 'postgresql':
        from sqlalchemy.dialects.postgresql import insert
    elif engine.dialect.name == 'sqlite':
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise ValueError('Usage limits require PostgreSQL or SQLite')
    reservations = [
        (['repository', repo_id, day], settings.repository_daily_limit, day),
        ([scope, actor, repo_id, day], daily, day),
        (['burst', actor, repo_id, minute], 5, minute),
    ]
    with engine.begin() as connection:
        # Old allowance counters contain no evidence; keep only the current day.
        connection.execute(delete(UsageBucket).where(UsageBucket.window < day))
        for identity, limit, window in reservations:
            key = hashlib.sha256('\0'.join(identity).encode()).hexdigest()
            connection.execute(insert(UsageBucket).values(key=key, window=window, count=0).on_conflict_do_nothing())
            result = connection.execute(update(UsageBucket).where(UsageBucket.key == key, UsageBucket.count < limit)
                .values(count=UsageBucket.count + 1))
            if result.rowcount != 1:
                # The whole transaction rolls back, including other counters.
                raise ValueError('Model operation allowance reached. Wait before retrying or ask your workspace administrator.')
