# -*- coding: utf-8 -*-
"""
Regula de validare (extindere, fara "Nr." pe pagina publica de reguli):
codurile din RegulamentLocalUrbanism trebuie sa preexiste in straturile de
zone.

Gasita prin audit al codului sursa al validatorului oficial (cod_validare,
rule_type 49, functia `regulament_zones_unique_codes`), care nu se mapeaza
1:1 pe niciuna dintre cele 34 de reguli publicate - distincta de si mai
"lejera" decat corelarea exacta cod->tip pe care regula 19 o acopera deja
(care verifica perechea (cod, tip) completa). Aici se verifica doar
EXISTENTA codului, indiferent de tip: fiecare "Cod_ZF_ZRS" din
RegulamentLocalUrbanism trebuie sa existe fie ca "Cod_ZF" in ZFPropusa, fie
ca "Cod_ZRS" in ZonaReglementareSuplimentara.

Nefiind confirmata ca activa server-side pentru profilul PUG v3.0.0 (nu am
vizibilitate asupra tipurilor de regula efectiv activate), e inclusa aici ca
o verificare suplimentara utila, nu ca o garantie de paritate cu validatorul
oficial.
"""

from .base import BaseValidationRule, ValidationFailure
from .gpkg_utils import MAX_REPORTED, field_value_set, get_layer, is_null, request_for_fields

RLU_LAYER = "RegulamentLocalUrbanism"
RLU_CODE_FIELD = "Cod_ZF_ZRS"
ZF_LAYER = "ZFPropusa"
ZF_CODE_FIELD = "Cod_ZF"
ZRS_LAYER = "ZonaReglementareSuplimentara"
ZRS_CODE_FIELD = "Cod_ZRS"


class RluCodesPreexistRule(BaseValidationRule):
    """Fara parametri de configurare - numele straturilor/coloanelor sunt fixe."""

    def __init__(self, name, description="", rule_id=35):
        super().__init__(name, description, rule_id)

    def run(self, project):
        try:
            rlu_layer = get_layer(project, RLU_LAYER)
        except ValueError as exc:
            return [ValidationFailure(rule_name=self.name, layer_name=RLU_LAYER, fid=0, reason=str(exc))]

        valid_codes = set()
        for layer_name, code_field in ((ZF_LAYER, ZF_CODE_FIELD), (ZRS_LAYER, ZRS_CODE_FIELD)):
            try:
                layer = get_layer(project, layer_name)
            except ValueError:
                continue
            field_names = {f.name() for f in layer.fields()}
            if code_field in field_names:
                valid_codes |= field_value_set(layer, code_field)

        field_names = {f.name() for f in rlu_layer.fields()}
        if RLU_CODE_FIELD not in field_names:
            return []

        failures = []
        count = 0
        for feat in rlu_layer.getFeatures(request_for_fields(rlu_layer, [RLU_CODE_FIELD])):
            if count >= MAX_REPORTED:
                break
            code = feat[RLU_CODE_FIELD]
            if is_null(code):
                continue
            if code not in valid_codes:
                failures.append(
                    ValidationFailure(
                        rule_name=self.name,
                        layer_name=RLU_LAYER,
                        fid=feat.id(),
                        reason=(
                            f"Codul '{code}' din '{RLU_CODE_FIELD}' nu exista ca "
                            f"'{ZF_CODE_FIELD}' in '{ZF_LAYER}' nici ca '{ZRS_CODE_FIELD}' "
                            f"in '{ZRS_LAYER}'."
                        ),
                    )
                )
                count += 1

        return failures
