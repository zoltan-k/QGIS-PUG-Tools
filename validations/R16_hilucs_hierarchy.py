# -*- coding: utf-8 -*-
"""
Regula de validare: Se verifica coloanele HILUCS_N1, HILUCS_N2, HILUCS_N3
din straturile fisierului GPKG sa fie corelate conform OMDLPA 904.

Codurile si ierarhia HILUCS sunt citite din tabelul de referinta "_hilucs"
(coloane: cod, nivel, cod_parinte) inclus in sablonul GPKG.

Cache-ul ierarhiei HILUCS este LOCAL fiecarei rulari a run() (nu pe
instanta), altfel o a doua rulare a ACELEIASI instante de regula (deja
inregistrata la nivel de modul, deci reutilizata pentru toata sesiunea QGIS)
ar continua sa foloseasca ierarhia citita la prima rulare, chiar daca
tabelul de referinta s-a schimbat intre timp (ex. schimbarea sablonului
activ sau deschiderea altui proiect).
"""

from .base import BaseValidationRule, ValidationFailure
from .gpkg_utils import MAX_REPORTED, get_layer, get_layer_or_open, is_null, request_for_fields


class HilucsHierarchyRule(BaseValidationRule):
    """
    Parametrul `rules` este un dict {strat: [HILUCS_N1, HILUCS_N2, HILUCS_N3]}.
    """

    def __init__(self, name, rules, description="", rule_id=16):
        super().__init__(name, description, rule_id)
        self.rules = rules

    @staticmethod
    def _load_hilucs(project, hilucs_cache):
        if hilucs_cache["parents"] is not None:
            return hilucs_cache["parents"]
        ref_layer = get_layer_or_open(project, "_hilucs")
        parents = {}
        request = request_for_fields(ref_layer, ["cod", "cod_parinte"])
        for feat in ref_layer.getFeatures(request):
            cod = feat["cod"]
            if is_null(cod):
                continue
            parinte = feat["cod_parinte"]
            parents[cod] = None if is_null(parinte) else parinte
        hilucs_cache["parents"] = parents
        return parents

    def _validate_layer(self, project, hilucs_cache, layer_name, columns):
        failures = []
        try:
            layer = get_layer(project, layer_name)
        except ValueError:
            return failures
        if layer.featureCount() < 1:
            return failures

        field_names = {f.name() for f in layer.fields()}
        if not all(c in field_names for c in columns):
            return failures
        n1_col, n2_col, n3_col = columns

        parents = self._load_hilucs(project, hilucs_cache)

        request = request_for_fields(layer, columns)
        count = 0

        for feat in layer.getFeatures(request):
            if count >= MAX_REPORTED:
                break

            n1, n2, n3 = feat[n1_col], feat[n2_col], feat[n3_col]
            bad_columns = set()

            if is_null(n1):
                bad_columns.add(n1_col)
            elif n1 not in parents:
                bad_columns.add(n1_col)

            if not is_null(n2) and n2 not in parents:
                bad_columns.add(n2_col)
            if not is_null(n3) and n3 not in parents:
                bad_columns.add(n3_col)

            if not is_null(n1) and not is_null(n2) and n1 in parents and n2 in parents:
                if parents.get(n2) != n1:
                    bad_columns.add(n1_col)
                    bad_columns.add(n2_col)

            if not is_null(n2) and not is_null(n3) and n2 in parents and n3 in parents:
                if parents.get(n3) != n2:
                    bad_columns.add(n2_col)
                    bad_columns.add(n3_col)

            # N3 completat fara N2: parintele lui N3 trebuie sa fie N2 (nu se poate
            # sari un nivel) - mai strict decat textul publicat, care verifica
            # relatia doar cand ambele sunt prezente.
            if is_null(n2) and not is_null(n3):
                bad_columns.add(n2_col)
                bad_columns.add(n3_col)

            if bad_columns:
                failures.append(
                    ValidationFailure(
                        rule_name=self.name,
                        layer_name=layer_name,
                        fid=feat.id(),
                        reason=(
                            "Coduri/ierarhie HILUCS neconforma pentru coloanele: "
                            f"{', '.join(sorted(bad_columns))}."
                        ),
                    )
                )
                count += 1

        return failures

    def run(self, project):
        hilucs_cache = {"parents": None}
        all_failures = []
        for layer_name, columns in self.rules.items():
            all_failures.extend(self._validate_layer(project, hilucs_cache, layer_name, columns))
        return all_failures
