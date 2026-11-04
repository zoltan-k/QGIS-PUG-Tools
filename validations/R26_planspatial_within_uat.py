# -*- coding: utf-8 -*-
"""
Regula de validare: Se verifica daca planul spatial este in limita
administrativa.

Geometria limitei administrative a UAT-ului nu este preluata de la un
serviciu extern in timpul VALIDARII (asa cum descrie definitia tehnica
publicata), ci este deja disponibila in proiect ca strat de referinta
"~REF_UAT" - o singura entitate, cea a UAT-ului curent, preluata dinamic la
crearea proiectului (vezi tools/uat_boundary.py si tools/project_loader.py).
Acest strat NU mai este inclus static in sablonul GPKG (ar fi insemnat sa
bundlam un set national de date de ~70-120 MB) - daca lipseste din proiect
(ex. un proiect creat altfel decat prin "Proiect nou PUG"), regula esueaza
cu un mesaj clar in loc sa incerce un apel de retea in timpul validarii.
"""

from ..tools import settings
from .base import BaseValidationRule, ValidationFailure
from .gpkg_utils import MAX_REPORTED, get_layer, is_null, request_for_fields

BOUNDARY_LAYER = "~REF_UAT"
BOUNDARY_SIRUTA_FIELD = "SIRUTA"
# sub STRICT_TOLERANCE: trece fara observatie. Intre STRICT_TOLERANCE si
# pragul configurabil (implicit 10 m, vezi tools/settings.py - conform
# precizarilor tehnice OMDLPA 904): esec de tip WARNING, nu BLOCKER. Peste
# pragul configurabil: BLOCKER.
STRICT_TOLERANCE = settings.BOUNDARY_BUFFER_STRICT_M
BUFFER_SEGMENTS = 8


class PlanSpatialWithinUatRule(BaseValidationRule):
    """
    Parametrul `valoare_regula` este numele coloanei cu codul SIRUTA
    (implicit "SIRUTA"), iar stratul verificat este mereu "PlanSpatial".
    """

    def __init__(self, name, valoare_regula="SIRUTA", description="", rule_id=26):
        super().__init__(name, description, rule_id)
        self.siruta_field = valoare_regula
        self.layer_name = "PlanSpatial"

    @staticmethod
    def _as_int(value):
        if is_null(value):
            return None
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return None

    def run(self, project):
        layer = get_layer(project, self.layer_name)

        siruta_values = set()
        request = request_for_fields(layer, [self.siruta_field])
        for feature in layer.getFeatures(request):
            code = self._as_int(feature[self.siruta_field])
            if code is not None:
                siruta_values.add(code)

        if not siruta_values:
            return [
                ValidationFailure(
                    rule_name=self.name,
                    layer_name=self.layer_name,
                    fid=0,
                    reason=f"Stratul '{self.layer_name}' nu contine SIRUTA.",
                )
            ]
        if len(siruta_values) > 1:
            return [
                ValidationFailure(
                    rule_name=self.name,
                    layer_name=self.layer_name,
                    fid=0,
                    reason=(
                        f"Stratul '{self.layer_name}' contine mai multe valori SIRUTA "
                        f"distincte: {sorted(siruta_values)}."
                    ),
                )
            ]

        siruta_value = next(iter(siruta_values))

        try:
            boundary_layer = get_layer(project, BOUNDARY_LAYER)
        except ValueError:
            return [
                ValidationFailure(
                    rule_name=self.name,
                    layer_name=self.layer_name,
                    fid=0,
                    reason=(
                        f"Stratul de referinta '{BOUNDARY_LAYER}' nu este incarcat in "
                        "proiect - regula nu poate verifica limita administrativa. "
                        "Acest strat este creat automat de 'Proiect nou PUG'; daca "
                        "proiectul a fost creat altfel, adauga-l manual sau recreeaza "
                        "proiectul cu unealta din plugin."
                    ),
                )
            ]

        uat_geom = None
        for feature in boundary_layer.getFeatures():
            if self._as_int(feature[BOUNDARY_SIRUTA_FIELD]) == siruta_value:
                uat_geom = feature.geometry()
                break

        if uat_geom is None or uat_geom.isEmpty():
            return [
                ValidationFailure(
                    rule_name=self.name,
                    layer_name=self.layer_name,
                    fid=0,
                    reason=(
                        f"Nu s-a gasit limita administrativa pentru SIRUTA "
                        f"'{siruta_value}' in stratul de referinta '{BOUNDARY_LAYER}'."
                    ),
                )
            ]

        buffer_max = settings.get_boundary_buffer_m()
        uat_geom_strict = uat_geom.buffer(STRICT_TOLERANCE, BUFFER_SEGMENTS)
        uat_geom_relaxed = (
            uat_geom.buffer(buffer_max, BUFFER_SEGMENTS)
            if buffer_max > STRICT_TOLERANCE
            else uat_geom_strict
        )

        failures = []
        count = 0
        for feature in layer.getFeatures():
            if count >= MAX_REPORTED:
                break
            geom = feature.geometry()
            if geom is None or geom.isEmpty():
                failures.append(
                    ValidationFailure(
                        rule_name=self.name,
                        layer_name=self.layer_name,
                        fid=feature.id(),
                        reason=(
                            "Geometria lipseste sau nu se afla in interiorul limitei "
                            f"administrative a UAT-ului (SIRUTA {siruta_value})."
                        ),
                        severity="BLOCKER",
                    )
                )
                count += 1
                continue
            if geom.within(uat_geom_strict):
                continue
            if geom.within(uat_geom_relaxed):
                severity = "WARNING"
                reason = (
                    "Geometria nu se afla strict in interiorul limitei administrative "
                    f"a UAT-ului (SIRUTA {siruta_value}), dar in toleranta de "
                    f"{buffer_max:g} m."
                )
            else:
                severity = "BLOCKER"
                reason = (
                    "Geometria nu se afla in interiorul limitei administrative a "
                    f"UAT-ului (SIRUTA {siruta_value}), nici in toleranta de "
                    f"{buffer_max:g} m."
                )
            failures.append(
                ValidationFailure(
                    rule_name=self.name,
                    layer_name=self.layer_name,
                    fid=feature.id(),
                    reason=reason,
                    severity=severity,
                )
            )
            count += 1

        return failures
