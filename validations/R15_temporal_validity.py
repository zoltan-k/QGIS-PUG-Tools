# -*- coding: utf-8 -*-
"""
Regula de validare: Se verifica coloanele din straturile fisierului GPKG
care contin date temporale sa fie corecte din punct de vedere cronologic
fata de data curenta.

Pentru rolurile "aprob" (data aprobarii) si "revizie" (data reviziei) se
considera esuata orice valoare lipsa, neinterpretabila ca data, SAU
ulterioara datei curente (o aprobare/revizie nu poate fi datata in viitor).

Rolul "exp" (data expirarii) - comparatie cu data curenta adaugata dupa un
audit al codului sursa al validatorului oficial (cod_validare,
rule_type 24, temporal_data_validation()), care arata ca o inregistrare
deja expirata trebuie sa esueze; publicat aici e in doua variante, in
functie de rolurile configurate pentru strat:
    - "aprob" SI "exp" prezente (PlanSpatial, ZonaReglementareSuplimentara):
      esec DECAT DACA aprob < azi < exp (ambele stricte).
    - doar "exp" prezent (ZFPropusa): esec doar daca azi > exp (exp == azi
      trece).
"revizie" ramane comparat doar cu "nu e in viitor", ca pana acum.
"""

from datetime import date

from .base import BaseValidationRule, ValidationFailure
from .gpkg_utils import MAX_REPORTED, get_layer, parse_date, request_for_fields

FUTURE_NOT_ALLOWED_ROLES = {"aprob", "revizie"}


class TemporalValidityRule(BaseValidationRule):
    """
    Parametrul `rules` este un dict {strat: {rol: nume_coloana}}, cu
    rol in {"aprob", "exp", "revizie"}, toate optionale per strat.
    """

    def __init__(self, name, rules, description="", rule_id=15):
        super().__init__(name, description, rule_id)
        self.rules = rules

    def _validate_layer(self, project, layer_name, roles):
        failures = []
        try:
            layer = get_layer(project, layer_name)
        except ValueError:
            return failures
        if layer.featureCount() < 1:
            return failures

        field_names = {f.name() for f in layer.fields()}
        roles = {role: col for role, col in roles.items() if col in field_names}
        if not roles:
            return failures

        columns = list(roles.values())
        request = request_for_fields(layer, columns)
        today = date.today()
        count = 0
        # "aprob" si "exp" ambele configurate pentru strat: se aplica
        # semantica stricta comuna aprob < azi < exp, nu doar cate o
        # comparatie independenta per rol.
        joint_mode = "aprob" in roles and "exp" in roles

        for feat in layer.getFeatures(request):
            if count >= MAX_REPORTED:
                break
            failed = False
            reasons = []

            for role, column in roles.items():
                parsed = parse_date(feat[column])
                if parsed is None:
                    failed = True
                    reasons.append(f"'{column}' lipseste sau nu este o data valida")
                    continue

                if role == "aprob" and joint_mode:
                    if not (parsed < today):
                        failed = True
                        reasons.append(
                            f"'{column}' ({parsed.isoformat()}) nu este anterioara datei "
                            "curente (necesar: aprobare < azi < expirare)"
                        )
                elif role == "exp":
                    if joint_mode:
                        if not (today < parsed):
                            failed = True
                            reasons.append(
                                f"'{column}' ({parsed.isoformat()}) nu este ulterioara "
                                "datei curente (necesar: aprobare < azi < expirare)"
                            )
                    elif today > parsed:
                        failed = True
                        reasons.append(f"'{column}' ({parsed.isoformat()}) a expirat")
                elif role in FUTURE_NOT_ALLOWED_ROLES and parsed > today:
                    failed = True
                    reasons.append(f"'{column}' ({parsed.isoformat()}) este ulterioara datei curente")

            if failed:
                failures.append(
                    ValidationFailure(
                        rule_name=self.name,
                        layer_name=layer_name,
                        fid=feat.id(),
                        reason="; ".join(reasons),
                    )
                )
                count += 1

        return failures

    def run(self, project):
        all_failures = []
        for layer_name, roles in self.rules.items():
            all_failures.extend(self._validate_layer(project, layer_name, roles))
        return all_failures
