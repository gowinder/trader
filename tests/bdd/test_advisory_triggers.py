"""BDD tests for advisory trigger system"""

from pytest_bdd import scenarios

# Import step definitions
from .conftest_advisory_triggers import *  # noqa: F401,F403

scenarios("features/advisory_triggers.feature")
