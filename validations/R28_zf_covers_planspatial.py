# -*- coding: utf-8 -*-
"""
Regula de validare: Se verifica daca geometriile din zonele functionale
acopera planul spatial (comparatie de arii totale, toleranta 50 mp,
fara operatii geometrice de suprapunere efectiva).
"""

from .base import BaseValidationRule, ValidationFailure
from .gpkg_utils import find_gpkg_path, open_ogr_layer

REFERENCE_LAYER = "PlanSpatial"
AREA_TOLERANCE = 50.0


class ZFCoversPlanSpatialRule(BaseValidationRule):
    """
    Parametrul `valoare_regula` este un string cu nume de straturi separate prin virgula.
    """

    def __init__(self, name, valoare_regula, description="", rule_id=28):
        super().__init__(name, description, rule_id)
        self.layer_names = [n.strip() for n in valoare_regula.split(",") if n.strip()]

    @staticmethod
    def _total_area(ogr_layer):
        ogr_layer.ResetReading()
        total = 0.0
        for feature in ogr_layer:
            geom = feature.GetGeometryRef()
            if geom is not None:
                total += geom.GetArea()
        return total

    def run(self, project):
        gpkg_path = find_gpkg_path(project)
        ref_ds, ref_layer = open_ogr_layer(gpkg_path, REFERENCE_LAYER)
        reference_area = self._total_area(ref_layer)
        ref_ds = None

        failures = []
        for layer_name in self.layer_names:
            ds, ogr_layer = open_ogr_layer(gpkg_path, layer_name)
            layer_area = self._total_area(ogr_layer)
            ds = None

            if abs(layer_area - reference_area) > AREA_TOLERANCE:
                failures.append(
                    ValidationFailure(
                        rule_name=self.name,
                        layer_name=layer_name,
                        fid=0,
                        reason=(
                            f"Aria totala a stratului ({layer_area:.2f} mp) difera de aria "
                            f"stratului de referinta '{REFERENCE_LAYER}' ({reference_area:.2f} mp) "
                            f"cu mai mult decat toleranta de {AREA_TOLERANCE} mp."
                        ),
                    )
                )

        return failures
