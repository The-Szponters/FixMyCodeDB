"""
Labeling module for automatic code analysis and classification.
"""

from .labeler import Labeler
from .config_mapper import ConfigBasedMapper

__all__ = ["Labeler", "ConfigBasedMapper"]
