# -*- coding: utf-8 -*-
"""
Regula de validare: corelare (cod, tip) intre un strat sursa si un strat de
referinta (regulament), pe baza unui lookup construit din stratul de
referinta. Foloseste API-ul QGIS (QgsVectorLayer), deoarece straturile sunt
deja incarcate in proiectul activ.
"""

from qgis.core import QgsFeatureRequest, NULL

from .base import BaseValidationRule, ValidationFailure


class ReferenceCorrelationRule(BaseValidationRule):
    """
    Parametrul `rules` are formatul din valoare_regula original, ex:

    [
        {
            "layer": "RegulamentLocalUrbanism",
            "matches_fields_from": {"ZFPropusa": ["Cod_ZF", "Tip_ZF"]},
            "validated_fields": ["Cod_ZF_ZRS", "Tip_ZF_ZRS"],
        },
        ...
    ]
    """

    def __init__(self, name, rules, description="", rule_id = 19):
        super().__init__(name, description, rule_id)
        self.rules = rules

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _is_null(value):
        if value is None:
            return True
        try:
            return value == NULL
        except Exception:
            return False

    @staticmethod
    def _get_layer(project, layer_name):
        layers = project.mapLayersByName(layer_name)
        if not layers:
            raise ValueError(f"Stratul '{layer_name}' nu a fost gasit in proiect.")
        if len(layers) > 1:
            raise ValueError(
                f"Exista mai multe straturi cu numele '{layer_name}' in proiect; "
                "foloseste un identificator unic (layer id)."
            )
        return layers[0]

    @staticmethod
    def _request_for_fields(layer, field_names):
        request = QgsFeatureRequest()
        request.setSubsetOfAttributes(field_names, layer.fields())
        request.setFlags(QgsFeatureRequest.NoGeometry)
        return request

    def _build_lookup(self, ref_layer, code_field, type_field):
        lookup = {}
        request = self._request_for_fields(ref_layer, [code_field, type_field])
        for feat in ref_layer.getFeatures(request):
            key = feat[code_field]
            val = feat[type_field]
            if self._is_null(key):
                continue
            lookup[key] = val
        return lookup

    # -- core logic ----------------------------------------------------------

    def _validate_single_rule(self, project, rule):
        ref_layer_name = rule["layer"]
        matches = rule["matches_fields_from"]
        source_layer_name = next(iter(matches))
        source_fields = matches[source_layer_name]
        code_src_field, type_src_field = source_fields

        validated_fields = rule["validated_fields"]
        code_ref_field, type_ref_field = validated_fields

        ref_layer = self._get_layer(project, ref_layer_name)
        source_layer = self._get_layer(project, source_layer_name)

        ref_field_names = {f.name() for f in ref_layer.fields()}
        src_field_names = {f.name() for f in source_layer.fields()}

        missing_ref_fields = [f for f in validated_fields if f not in ref_field_names]
        missing_src_fields = [f for f in source_fields if f not in src_field_names]

        failures = []

        if missing_ref_fields:
            raise ValueError(
                f"Campurile de validare {missing_ref_fields} lipsesc din stratul de "
                f"referinta '{ref_layer_name}'."
            )

        if missing_src_fields:
            for feat in source_layer.getFeatures():
                failures.append(
                    ValidationFailure(
                        rule_name=self.name,
                        layer_name=source_layer_name,
                        fid=feat.id(),
                        reason=(
                            f"Campurile sursa {missing_src_fields} lipsesc din schema "
                            f"stratului '{source_layer_name}'."
                        ),
                    )
                )
            return failures

        lookup = self._build_lookup(ref_layer, code_ref_field, type_ref_field)

        request = self._request_for_fields(source_layer, [code_src_field, type_src_field])
        for feat in source_layer.getFeatures(request):
            code_val = feat[code_src_field]
            type_val = feat[type_src_field]

            if self._is_null(code_val) or self._is_null(type_val):
                failures.append(
                    ValidationFailure(
                        rule_name=self.name,
                        layer_name=source_layer_name,
                        fid=feat.id(),
                        reason=(
                            f"Valoare NULL in campurile '{code_src_field}'/"
                            f"'{type_src_field}'."
                        ),
                    )
                )
                continue

            if code_val not in lookup:
                failures.append(
                    ValidationFailure(
                        rule_name=self.name,
                        layer_name=source_layer_name,
                        fid=feat.id(),
                        reason=(
                            f"Perechea ({code_val}, {type_val}) nu exista in stratul "
                            f"de referinta '{ref_layer_name}': '{code_src_field}'="
                            f"{code_val} nu are corespondent in '{code_ref_field}'."
                        ),
                    )
                )
                continue

            if lookup[code_val] != type_val:
                failures.append(
                    ValidationFailure(
                        rule_name=self.name,
                        layer_name=source_layer_name,
                        fid=feat.id(),
                        reason=(
                            f"Tip neconcordant pentru cod '{code_val}': sursa are "
                            f"'{type_val}', referinta '{ref_layer_name}' are "
                            f"'{lookup[code_val]}'."
                        ),
                    )
                )

        return failures

    def missing_pairs(self, project):
        """
        Perechile (cod, tip) din straturile sursa al caror COD lipseste complet
        din stratul de referinta (esecul "nu are corespondent"), fara plafon,
        deduplicate pe cod. NU include NULL-uri in sursa si nici nepotrivirile
        de tip pentru un cod existent (acolo nu exista o singura valoare
        corecta - un rand nou ar duplica codul).

        Returneaza o lista de dict-uri:
        {ref_layer, code_field, type_field, code, type, source_layer}
        Folosit de fix-ul de pre-populare (tools/rule_fixes.py).
        """
        out = []
        seen = set()
        for rule in self.rules:
            ref_layer_name = rule["layer"]
            source_layer_name = next(iter(rule["matches_fields_from"]))
            code_src, type_src = rule["matches_fields_from"][source_layer_name]
            code_ref, type_ref = rule["validated_fields"]
            try:
                ref_layer = self._get_layer(project, ref_layer_name)
                source_layer = self._get_layer(project, source_layer_name)
            except ValueError:
                continue
            ref_names = {f.name() for f in ref_layer.fields()}
            src_names = {f.name() for f in source_layer.fields()}
            if code_ref not in ref_names or type_ref not in ref_names:
                continue
            if code_src not in src_names or type_src not in src_names:
                continue
            lookup = self._build_lookup(ref_layer, code_ref, type_ref)
            request = self._request_for_fields(source_layer, [code_src, type_src])
            for feat in source_layer.getFeatures(request):
                code_val, type_val = feat[code_src], feat[type_src]
                if self._is_null(code_val) or self._is_null(type_val):
                    continue
                if code_val in lookup:
                    continue
                key = (ref_layer_name, code_val)
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    {
                        "ref_layer": ref_layer_name,
                        "code_field": code_ref,
                        "type_field": type_ref,
                        "code": code_val,
                        "type": type_val,
                        "source_layer": source_layer_name,
                    }
                )
        return out

    def run(self, project):
        all_failures = []
        for rule in self.rules:
            all_failures.extend(self._validate_single_rule(project, rule))
        return all_failures
