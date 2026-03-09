"""BDD tests for signal filter (anti-overtrading)"""

from pytest_bdd import scenarios

# Import step definitions
from .conftest_signal_filter import *  # noqa: F401,F403

scenarios("features/signal_filter.feature")
