"""Shared Dramatiq broker for all background job actors.

Every imported actor must register on the same broker instance.  Creating a
broker separately in each job module makes the Dramatiq CLI select the broker
from its first module while the other actors remain registered on different
broker instances.
"""

from gameclub_backend.config import get_settings
from gameclub_backend.infrastructure.broker import configure_broker

broker = configure_broker(get_settings())
