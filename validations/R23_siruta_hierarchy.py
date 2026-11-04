# -*- coding: utf-8 -*-
"""
Regula de validare: Se verifica daca SIRUTA din stratul PlanSpatial este
SIRUTA superioara (la nivel de UAT) pentru valorile SIRUTA din straturile
LimitaIntravilanExistenta si LimitaIntravilanPropusa (la nivel de localitate).

Ierarhia SIRUTA este dedusa local din tabelul de referinta "_siruta" inclus
in sablonul GPKG, in loc de un apel catre un serviciu extern. Incepand cu
sablonul 3.0.3, "_siruta" nu mai e o tabela ierarhica pe 3 niveluri (judet/
UAT/localitate, cu auto-referinta "siruta"/"sirsup") - e o lista plata de
localitati, fiecare purtand direct codul UAT-ului parinte (coloanele
"siruta_loc" = codul localitatii, "siruta_uat" = codul UAT-ului careia ii
apartine). Verificarea "un cod SIRUTA e subordonat unui cod SIRUTA parinte"
foloseste acum aceste doua coloane in loc de "siruta"/"sirsup".
"""

from .base import BaseValidationRule, ValidationFailure
from .gpkg_utils import MAX_REPORTED, get_layer, get_layer_or_open, is_null, request_for_fields


class SirutaHierarchyRule(BaseValidationRule):
    """
    Parametrul `rules` este un dict:
        {"source_layer": strat, "source_fields": [camp_siruta, ...],
         "validated_layers": [{"layer": strat, "fields": [camp_siruta, ...]}, ...]}
    """

    def __init__(self, name, rules, description="", rule_id=23):
        super().__init__(name, description, rule_id)
        self.rules = rules

    @staticmethod
    def _as_int(value):
        if is_null(value):
            return None
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return None

    def _children_of(self, project, parent_codes):
        ref_layer = get_layer_or_open(project, "_siruta")
        children = set()
        request = request_for_fields(ref_layer, ["siruta_loc", "siruta_uat"])
        for feat in ref_layer.getFeatures(request):
            siruta_uat = self._as_int(feat["siruta_uat"])
            if siruta_uat is not None and siruta_uat in parent_codes:
                siruta_loc = self._as_int(feat["siruta_loc"])
                if siruta_loc is not None:
                    children.add(siruta_loc)
        return children

    def _validate_single_rule(self, project, rule):
        failures = []
        source_layer_name = rule["source_layer"]
        source_siruta_field = rule["source_fields"][0]

        try:
            source_layer = get_layer(project, source_layer_name)
        except ValueError:
            return failures

        parent_codes = set()
        request = request_for_fields(source_layer, [source_siruta_field])
        for feat in source_layer.getFeatures(request):
            code = self._as_int(feat[source_siruta_field])
            if code is not None:
                parent_codes.add(code)

        if not parent_codes:
            failures.append(
                ValidationFailure(
                    rule_name=self.name,
                    layer_name=source_layer_name,
                    fid=0,
                    reason=f"Stratul '{source_layer_name}' nu contine coduri SIRUTA valide.",
                )
            )
            return failures

        valid_children = self._children_of(project, parent_codes)

        for validated in rule["validated_layers"]:
            layer_name = validated["layer"]
            siruta_field = validated["fields"][0]
            try:
                layer = get_layer(project, layer_name)
            except ValueError:
                continue
            if siruta_field not in {f.name() for f in layer.fields()}:
                continue

            request = request_for_fields(layer, [siruta_field])
            count = 0
            for feat in layer.getFeatures(request):
                if count >= MAX_REPORTED:
                    break
                code = self._as_int(feat[siruta_field])
                if code is None or code not in valid_children:
                    failures.append(
                        ValidationFailure(
                            rule_name=self.name,
                            layer_name=layer_name,
                            fid=feat.id(),
                            reason=(
                                f"Codul SIRUTA '{feat[siruta_field]}' nu este subordonat "
                                f"niciunui cod SIRUTA din '{source_layer_name}'."
                            ),
                        )
                    )
                    count += 1

        return failures

    def run(self, project):
        all_failures = []
        all_failures.extend(self._validate_single_rule(project, self.rules))
        return all_failures
