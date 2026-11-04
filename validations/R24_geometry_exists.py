# -*- coding: utf-8 -*-
"""
Regula de validare: Se verifica geometriile din straturile fisierului GPKG
sa existe si ca valoarea lor sa nu fie NULL.

Prioritate de raportare: straturile goale (fara nicio inregistrare) au
prioritate asupra geometriilor NULL - daca exista straturi goale, doar
acestea sunt raportate.
"""

from .base import BaseValidationRule, ValidationFailure
from .gpkg_utils import MAX_REPORTED, find_gpkg_path, open_ogr_layer


class GeometryExistsRule(BaseValidationRule):
    """
    Parametrul `valoare_regula` este un string cu nume de straturi separate prin virgula.
    """

    def __init__(self, name, valoare_regula, description="", rule_id=24):
        super().__init__(name, description, rule_id)
        self.layer_names = [n.strip() for n in valoare_regula.split(",") if n.strip()]

    def run(self, project):
        gpkg_path = find_gpkg_path(project)
        empty_layers = []
        null_geom_failures = []
        empty_geom_warnings = []  # extensie (WARNING) - raportate si cand exista straturi goale

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
                if geom is None:
                    null_geom_failures.append(
                        ValidationFailure(
                            rule_name=self.name,
                            layer_name=layer_name,
                            fid=feature.GetFID(),
                            reason="Geometria este NULL.",
                        )
                    )
                    count += 1
                elif geom.IsEmpty():
                    # extensie fata de regula publicata (care verifica doar NULL):
                    # o geometrie goala (ex. POLYGON EMPTY) nu e NULL, dar nu
                    # reprezinta nimic - doar avertisment, ca sa nu devina o
                    # respingere pe care validatorul oficial nu o face.
                    empty_geom_warnings.append(
                        ValidationFailure(
                            rule_name=self.name,
                            layer_name=layer_name,
                            fid=feature.GetFID(),
                            reason="Geometria este goala (EMPTY).",
                            severity="WARNING",
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
            ] + empty_geom_warnings

        return null_geom_failures + empty_geom_warnings
