# -*- coding: utf-8 -*-
"""
Regula de validare: Se verifica daca geometriile din fisierul GPKG au aria
egala cu cea din coloana specifica ariei.

Pentru PlanSpatial, LimitaIntravilanExistenta si LimitaIntravilanPropusa
aria se calculeaza in hectare (mp / 10000); pentru ZFExistenta si
ZonaReglementareSuplimentara, in metri patrati - conform definitiei tehnice
publicate. Toleranta: 0.1 din unitatea de masura a stratului.
"""

from .base import BaseValidationRule, ValidationFailure
from .gpkg_utils import MAX_REPORTED, find_gpkg_path, open_ogr_layer

HECTARE_LAYERS = {"PlanSpatial", "LimitaIntravilanExistenta", "LimitaIntravilanPropusa"}
TOLERANCE = 0.1


class AreaMatchesColumnRule(BaseValidationRule):
    """
    Parametrul `rules` este un dict {strat: coloana_arie}.
    """

    def __init__(self, name, rules, description="", rule_id=32):
        super().__init__(name, description, rule_id)
        self.rules = rules

    def _validate_layer(self, gpkg_path, layer_name, area_field):
        failures = []
        ds, ogr_layer = open_ogr_layer(gpkg_path, layer_name)

        field_index = ogr_layer.GetLayerDefn().GetFieldIndex(area_field)
        if field_index < 0:
            ds = None
            return failures

        in_hectare = layer_name in HECTARE_LAYERS
        divisor = 10000.0 if in_hectare else 1.0
        unit = "ha" if in_hectare else "mp"

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
                        reason=f"Geometria sau valoarea coloanei '{area_field}' lipseste.",
                    )
                )
                count += 1
                continue

            computed = round(geom.GetArea() / divisor, 2)
            if abs(computed - float(stored)) > TOLERANCE:
                failures.append(
                    ValidationFailure(
                        rule_name=self.name,
                        layer_name=layer_name,
                        fid=feature.GetFID(),
                        reason=(
                            f"Aria calculata ({computed} {unit}) difera de valoarea din "
                            f"coloana '{area_field}' ({stored} {unit}) cu mai mult decat "
                            f"toleranta de {TOLERANCE} {unit}."
                        ),
                    )
                )
                count += 1

        ds = None
        return failures

    def run(self, project):
        gpkg_path = find_gpkg_path(project)
        failures = []
        for layer_name, area_field in self.rules.items():
            failures.extend(self._validate_layer(gpkg_path, layer_name, area_field))
        return failures
