"""BDD tests for event detection and cooldown management"""

from pytest_bdd import scenarios

# Import step definitions
from .conftest_event_detection import *  # noqa: F401,F403

scenarios("features/event_detection.feature")
