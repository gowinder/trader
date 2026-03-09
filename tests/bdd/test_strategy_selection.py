"""BDD tests for strategy selection and market classification"""

from pytest_bdd import scenarios

# Import step definitions
from .conftest_strategy_selection import *  # noqa: F401,F403

scenarios("features/strategy_selection.feature")
