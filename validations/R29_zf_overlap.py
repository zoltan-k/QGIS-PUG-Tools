# -*- coding: utf-8 -*-
"""
Regula de validare: Se verifica daca geometriile din zonele functionale se
suprapun.

Fiecare geometrie este erodata cu -0.1 m (Buffer(-0.1)) inainte de testare,
pentru a elimina falsele pozitive cauzate de margini comune. Perechile de
geometrii sunt pre-filtrate dupa suprapunerea bounding box-urilor (echivalent
functional cu filtrarea spatiala descrisa in definitia tehnica publicata,
fara a construi explicit un strat in memorie), apoi testate cu
Intersects() AND NOT Touches().
"""

from .base import BaseValidationRule, ValidationFailure
from .gpkg_utils import MAX_REPORTED, find_gpkg_path, open_ogr_layer

EROSION = -0.1


class ZFOverlapRule(BaseValidationRule):
    """
    Parametrul `valoare_regula` este un string cu nume de straturi separate prin virgula.
    """

    def __init__(self, name, valoare_regula, description="", rule_id=29):
        super().__init__(name, description, rule_id)
        self.layer_names = [n.strip() for n in valoare_regula.split(",") if n.strip()]

    @staticmethod
    def _envelopes_overlap(env_a, env_b):
        min_x_a, max_x_a, min_y_a, max_y_a = env_a
        min_x_b, max_x_b, min_y_b, max_y_b = env_b
        return not (max_x_a < min_x_b or max_x_b < min_x_a or max_y_a < min_y_b or max_y_b < min_y_a)

    def _validate_layer(self, ds, ogr_layer, layer_name):
        ogr_layer.ResetReading()
        prepared = []
        for feature in ogr_layer:
            geom = feature.GetGeometryRef()
            if geom is None:
                continue
            eroded = geom.Buffer(EROSION)
            if eroded is None or eroded.IsEmpty():
                continue
            prepared.append((feature.GetFID(), eroded, eroded.GetEnvelope()))

        failures = []
        reported = 0
        for i in range(len(prepared)):
            if reported >= MAX_REPORTED:
                break
            fid_a, geom_a, env_a = prepared[i]
            for j in range(i + 1, len(prepared)):
                if reported >= MAX_REPORTED:
                    break
                fid_b, geom_b, env_b = prepared[j]
                if not self._envelopes_overlap(env_a, env_b):
                    continue
                if geom_a.Intersects(geom_b) and not geom_a.Touches(geom_b):
                    failures.append(
                        ValidationFailure(
                            rule_name=self.name,
                            layer_name=layer_name,
                            fid=fid_a,
                            reason=f"Geometria se suprapune cu FID {fid_b} din acelasi strat.",
                        )
                    )
                    reported += 1

        return failures

    def run(self, project):
        gpkg_path = find_gpkg_path(project)
        failures = []
        for layer_name in self.layer_names:
            ds, ogr_layer = open_ogr_layer(gpkg_path, layer_name)
            failures.extend(self._validate_layer(ds, ogr_layer, layer_name))
            ds = None
        return failures
