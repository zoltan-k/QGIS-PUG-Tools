# -*- coding: utf-8 -*-
"""
Regula de validare: Se verifica geometriile din straturile fisierului GPKG
sa fie valide (GEOS IsValid(), via GDAL/OGR).

Prioritate de raportare: straturile goale au prioritate asupra geometriilor
invalide - daca exista straturi goale, doar acestea sunt raportate.
"""

from .base import BaseValidationRule, ValidationFailure
from .gpkg_utils import MAX_REPORTED, find_gpkg_path, open_ogr_layer


class GeometryValidRule(BaseValidationRule):
    """
    Parametrul `valoare_regula` este un string cu nume de straturi separate prin virgula.
    """

    def __init__(self, name, valoare_regula, description="", rule_id=25):
        super().__init__(name, description, rule_id)
        self.layer_names = [n.strip() for n in valoare_regula.split(",") if n.strip()]

    def run(self, project):
        gpkg_path = find_gpkg_path(project)
        empty_layers = []
        invalid_geom_failures = []

        for layer_name in self.layer_names:
            ds, ogr_layer = open_ogr_layer(gpkg_path, layer_name)

            if ogr_layer.GetFeatureCount() < 1:
                empty_layers.append(layer_name)
                ds = None
                continue

            ogr_layer.ResetReading()
            count = 0
            for feature in ogr_layer:
                if count >= MAX_REPORTED:
                    break
                geom = feature.GetGeometryRef()
                if geom is None or not geom.IsValid():
                    invalid_geom_failures.append(
                        ValidationFailure(
                            rule_name=self.name,
                            layer_name=layer_name,
                            fid=feature.GetFID(),
                            reason="Geometria lipseste sau este invalida (GEOS IsValid()=False).",
                        )
                    )
                    count += 1
            ds = None

        if empty_layers:
            return [
                ValidationFailure(
                    rule_name=self.name,
                    layer_name=layer_name,
                    fid=0,
                    reason=f"Stratul '{layer_name}' nu contine date.",
                )
                for layer_name in empty_layers
            ]

        return invalid_geom_failures
