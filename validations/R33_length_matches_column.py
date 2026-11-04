# -*- coding: utf-8 -*-
"""
Regula de validare: Se verifica daca geometriile din fisierul GPKG au
lungimea egala cu cea din coloana specifica lungimii (toleranta 0.1 m).
"""

from .base import BaseValidationRule, ValidationFailure
from .gpkg_utils import MAX_REPORTED, find_gpkg_path, open_ogr_layer

TOLERANCE = 0.1


class LengthMatchesColumnRule(BaseValidationRule):
    """
    Parametrul `rules` este un dict {strat: coloana_lungime}.
    """

    def __init__(self, name, rules, description="", rule_id=33):
        super().__init__(name, description, rule_id)
        self.rules = rules

    def _validate_layer(self, gpkg_path, layer_name, length_field):
        failures = []
        ds, ogr_layer = open_ogr_layer(gpkg_path, layer_name)

        field_index = ogr_layer.GetLayerDefn().GetFieldIndex(length_field)
        if field_index < 0:
            ds = None
            return failures

        ogr_layer.ResetReading()
        count = 0
        for feature in ogr_layer:
            if count >= MAX_REPORTED:
                break
            geom = feature.GetGeometryRef()
            stored = feature.GetField(field_index)
            if geom is None or stored is None:
                failures.append(
                    ValidationFailure(
                        rule_name=self.name,
                        layer_name=layer_name,
                        fid=feature.GetFID(),
                        reason=f"Geometria sau valoarea coloanei '{length_field}' lipseste.",
                    )
                )
                count += 1
                continue

            computed = round(geom.Length(), 2)
            if abs(computed - float(stored)) > TOLERANCE:
                failures.append(
                    ValidationFailure(
                        rule_name=self.name,
                        layer_name=layer_name,
                        fid=feature.GetFID(),
                        reason=(
                            f"Lungimea calculata ({computed} m) difera de valoarea din "
                            f"coloana '{length_field}' ({stored} m) cu mai mult decat "
                            f"toleranta de {TOLERANCE} m."
                        ),
                    )
                )
                count += 1

        ds = None
        return failures

    def run(self, project):
        gpkg_path = find_gpkg_path(project)
        failures = []
        for layer_name, length_field in self.rules.items():
            failures.extend(self._validate_layer(gpkg_path, layer_name, length_field))
        return failures
