# -*- coding: utf-8 -*-
"""
Regula de validare (extindere, fara "Nr." pe pagina publica de reguli):
consistenta cod->tip in interiorul aceluiasi strat.

Gasita prin audit al codului sursa al validatorului oficial (cod_validare,
rule_type 53, functia `zones_code_type_consistency`), care nu se mapeaza
1:1 pe niciuna dintre cele 34 de reguli publicate. Verifica, pentru fiecare
pereche (coloana_cod, coloana_tip) dintr-un strat, ca aceeasi valoare de cod
nu apare niciodata cu doua valori de tip diferite pe randuri diferite - NU e
aceeasi verificare cu unicitatea cod/tip din regula 17 (care verifica ca
fiecare VALOARE dintr-o coloana e unica in strat; aici codul poate aparea de
mai multe ori, doar tipul asociat trebuie sa fie mereu acelasi).

Numele regulii oficiale ("zones_") si straturile discutate in acelasi
context in codul sursa sugereaza ca se aplica familiei de straturi
zona/subzona (ZF, ZRS si straturile de regulament asociate) - straturile
exacte nu erau explicit enumerate in sursa examinata, asa ca acest plugin
acopera toate perechile cod/tip deja folosite in celelalte reguli pentru
aceasta familie de straturi.

Nefiind confirmata ca activa server-side pentru profilul PUG v3.0.0, e
inclusa aici ca o verificare suplimentara utila, nu ca o garantie de
paritate cu validatorul oficial.
"""

from .base import BaseValidationRule, ValidationFailure
from .gpkg_utils import MAX_REPORTED, get_layer, is_null, request_for_fields


class ZonesCodeTypeConsistencyRule(BaseValidationRule):
    """
    Parametrul `valoare_regula` este un dict {strat: [(coloana_cod, coloana_tip), ...]}.
    """

    def __init__(self, name, valoare_regula, description="", rule_id=36):
        super().__init__(name, description, rule_id)
        self.rules = valoare_regula

    def _validate_pair(self, layer, layer_name, code_col, type_col):
        field_names = {f.name() for f in layer.fields()}
        if code_col not in field_names or type_col not in field_names:
            return []

        code_to_type = {}
        code_to_fids = {}
        for feat in layer.getFeatures(request_for_fields(layer, [code_col, type_col])):
            code = feat[code_col]
            typ = feat[type_col]
            if is_null(code) or is_null(typ):
                continue
            if code not in code_to_type:
                code_to_type[code] = typ
                code_to_fids[code] = [feat.id()]
            elif code_to_type[code] != typ:
                code_to_fids[code].append(feat.id())

        failures = []
        count = 0
        for code, fids in code_to_fids.items():
            if count >= MAX_REPORTED:
                break
            if len(fids) < 2:
                continue
            failures.append(
                ValidationFailure(
                    rule_name=self.name,
                    layer_name=layer_name,
                    fid=fids[0],
                    reason=(
                        f"Codul '{code}' din '{code_col}' apare cu tipuri diferite in "
                        f"coloana '{type_col}' (randuri fid: {fids[:MAX_REPORTED]})."
                    ),
                )
            )
            count += 1
        return failures

    def run(self, project):
        all_failures = []
        for layer_name, pairs in self.rules.items():
            try:
                layer = get_layer(project, layer_name)
            except ValueError:
                continue
            if layer.featureCount() < 1:
                continue
            for code_col, type_col in pairs:
                all_failures.extend(self._validate_pair(layer, layer_name, code_col, type_col))
        return all_failures
