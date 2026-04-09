"""Alerting service for detection spikes."""

from core.database import RedisClient
from core.logger import logger


async def check_and_send_alert(account_id: str, event: dict):
  """Checks for a detection spike and logs an alert if necessary."""
  redis = RedisClient()
  key = f"alerts:{account_id}:spike_count"
  
  # Increment count for this account in the last 5 minutes
  count = await redis.incr(key)
  if count == 1:
    await redis.expire(key, 300)  # 5 minutes window

  if count >= 10:
    # Trigger alert (log for now)
    logger.warning(
      f"ALERT: Detection spike detected for account {account_id}! "
      f"{count} high-confidence detections in the last 5 minutes."
    )
    # Reset count so we don't spam every single event after 10
    await redis.delete(key)
