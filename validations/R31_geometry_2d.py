# -*- coding: utf-8 -*-
"""
Regula de validare: Se verifica geometriile din fisierul GPKG sa contina
coordonatele corecte (longitudine, latitudine) - fara coordonate de
lungime/masura (M) sau altitudine (Z).
"""

from .base import BaseValidationRule, ValidationFailure
from .gpkg_utils import MAX_REPORTED, find_gpkg_path, open_ogr_layer


class Geometry2DRule(BaseValidationRule):
    """
    Parametrul `valoare_regula` este un string cu nume de straturi separate prin virgula.
    """

    def __init__(self, name, valoare_regula, description="", rule_id=31):
        super().__init__(name, description, rule_id)
        self.layer_names = [n.strip() for n in valoare_regula.split(",") if n.strip()]

    def run(self, project):
        gpkg_path = find_gpkg_path(project)
        failures = []

        for layer_name in self.layer_names:
            ds, ogr_layer = open_ogr_layer(gpkg_path, layer_name)
            ogr_layer.ResetReading()
            count = 0
            for feature in ogr_layer:
                if count >= MAX_REPORTED:
                    break
                geom = feature.GetGeometryRef()
                if geom is None or geom.Is3D() or geom.IsMeasured():
                    failures.append(
                        ValidationFailure(
                            rule_name=self.name,
                            layer_name=layer_name,
                            fid=feature.GetFID(),
                            reason=(
                                "Geometria lipseste sau nu este strict bidimensionala "
                                "(contine coordonate Z si/sau M)."
                            ),
                        )
                    )
                    count += 1
            ds = None

        return failures
