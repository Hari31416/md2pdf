"""StyleRegistry — layered stylesheet merge for theme and plugin overrides.

The pipeline builds a stylesheet from the default theme, then lets plugins
add their own layers on top.  Later layers win on key collisions so that
plugin styles always override defaults.

Usage::

    registry = StyleRegistry()
    registry.add_layer(build_default_stylesheet(theme))
    registry.add_layer(plugin.get_stylesheet())   # plugin layer wins
    styles = registry.build()

"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class StyleRegistry:
    """Accumulates stylesheet layers and merges them into a single dict.

    Each layer is a flat ``dict`` with the same structure as the dict returned
    by :func:`~md2pdf.styles.default.build_default_stylesheet`.  Layers added
    later override keys from earlier layers.
    """

    def __init__(self) -> None:
        self._layers: list[dict] = []

    def add_layer(self, styles: dict) -> None:
        """Append a stylesheet layer.

        Args:
            styles: Flat stylesheet dict.  Its keys will override any
                identically named keys from previously added layers.
        """
        self._layers.append(styles)
        logger.debug("StyleRegistry: added layer with %d keys", len(styles))

    def build(self) -> dict:
        """Merge all layers and return the combined stylesheet.

        Returns:
            A new dict containing all keys from all layers.  When the same
            key appears in multiple layers, the **last** layer wins.
        """
        merged: dict = {}
        for layer in self._layers:
            merged.update(layer)
        return merged
