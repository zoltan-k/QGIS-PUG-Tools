# -*- coding: utf-8 -*-
"""
Regula de validare: Se verifica daca geometriile din straturile fisierului
GPKG sunt in limita planul spatial (stratul de referinta este mereu
"PlanSpatial", cu un buffer de toleranta de 0.1 m).
"""

from ..tools import settings
from .base import BaseValidationRule, ValidationFailure
from .gpkg_utils import MAX_REPORTED, find_gpkg_path, open_ogr_layer

REFERENCE_LAYER = "PlanSpatial"
# vezi R26_planspatial_within_uat.py pentru explicatia celor doua praguri.
STRICT_TOLERANCE = settings.BOUNDARY_BUFFER_STRICT_M


class GeometryWithinPlanSpatialRule(BaseValidationRule):
    """
    Parametrul `valoare_regula` este un string cu nume de straturi separate prin virgula.
    """

    def __init__(self, name, valoare_regula, description="", rule_id=27):
        super().__init__(name, description, rule_id)
        self.layer_names = [n.strip() for n in valoare_regula.split(",") if n.strip()]

    @staticmethod
    def _reference_union(ref_layer):
        ref_layer.ResetReading()
        union_geom = None
        for feature in ref_layer:
            geom = feature.GetGeometryRef()
            if geom is None:
                continue
            union_geom = geom.Clone() if union_geom is None else union_geom.Union(geom)
        return union_geom

    def run(self, project):
        gpkg_path = find_gpkg_path(project)
        ref_ds, ref_layer = open_ogr_layer(gpkg_path, REFERENCE_LAYER)
        union_geom = self._reference_union(ref_layer)
        ref_ds = None

        if union_geom is None:
            return [
                ValidationFailure(
                    rule_name=self.name,
                    layer_name=REFERENCE_LAYER,
                    fid=0,
                    reason=f"Stratul de referinta '{REFERENCE_LAYER}' nu are geometrii valide.",
                )
            ]

        buffer_max = settings.get_boundary_buffer_m()
        union_geom_strict = union_geom.Buffer(STRICT_TOLERANCE)
        union_geom_relaxed = (
            union_geom.Buffer(buffer_max) if buffer_max > STRICT_TOLERANCE else union_geom_strict
        )

        failures = []
        for layer_name in self.layer_names:
            ds, ogr_layer = open_ogr_layer(gpkg_path, layer_name)
            ogr_layer.ResetReading()
            count = 0
            for feature in ogr_layer:
                if count >= MAX_REPORTED:
                    break
                geom = feature.GetGeometryRef()
                if geom is None:
                    failures.append(
                        ValidationFailure(
                            rule_name=self.name,
                            layer_name=layer_name,
                            fid=feature.GetFID(),
                            reason=f"Geometria lipseste (strat de referinta '{REFERENCE_LAYER}').",
                            severity="BLOCKER",
                        )
                    )
                    count += 1
                    continue
                if geom.Within(union_geom_strict):
                    continue
                if geom.Within(union_geom_relaxed):
                    severity = "WARNING"
                    reason = (
                        f"Geometria nu se afla strict in limita stratului '{REFERENCE_LAYER}', "
                        f"dar in toleranta de {buffer_max:g} m."
                    )
                else:
                    severity = "BLOCKER"
                    reason = (
                        f"Geometria nu se afla in limita stratului '{REFERENCE_LAYER}', "
                        f"nici in toleranta de {buffer_max:g} m."
                    )
                failures.append(
                    ValidationFailure(
                        rule_name=self.name,
                        layer_name=layer_name,
                        fid=feature.GetFID(),
                        reason=reason,
                        severity=severity,
                    )
                )
                count += 1
            ds = None

        return failures
