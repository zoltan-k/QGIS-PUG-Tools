# -*- coding: utf-8 -*-
"""
Configurarea regulilor de validare active in plugin.

Pentru a adauga o regula noua:
    1. Scrie o clasa noua in validations/, mostenind BaseValidationRule
       (vezi R19_reference_rules.py si R30_sliver_polygons.py ca exemple).
    2. Importa clasa aici si apeleaza register_rule(...) cu o instanta
       configurata cu parametrii tai.

Nu este nevoie sa modifici plugin.py sau restul plugin-ului.
"""

from .registry import register_rule
from .R10_gpkg_structure import GpkgStructureMatchesTemplateRule
from .R11_layer_check import LayerDataRule
from .R12_column_data_check import ColumnDataRule
from .R13_allowed_values import AllowedValuesRule
from .R14_value_pattern import ValuePatternRule
from .R15_temporal_validity import TemporalValidityRule
from .R16_hilucs_hierarchy import HilucsHierarchyRule
from .R17_unique_values import UniqueValuesRule
from .R18_consistent_temporal import ConsistentTemporalRule
from .R19_reference_rules import ReferenceCorrelationRule
from .R20_planspatial_temporal_match import PlanSpatialTemporalMatchRule
from .R21_zf_period_overlap import ZFPeriodOverlapRule
from .R22_pair_membership import PairMembershipRule
from .R23_siruta_hierarchy import SirutaHierarchyRule
from .R24_geometry_exists import GeometryExistsRule
from .R25_geometry_valid import GeometryValidRule
from .R26_planspatial_within_uat import PlanSpatialWithinUatRule
from .R27_geometry_within_planspatial import GeometryWithinPlanSpatialRule
from .R28_zf_covers_planspatial import ZFCoversPlanSpatialRule
from .R29_zf_overlap import ZFOverlapRule
from .R30_sliver_polygons import SliverPolygonRule
from .R31_geometry_2d import Geometry2DRule
from .R32_area_matches_column import AreaMatchesColumnRule
from .R33_length_matches_column import LengthMatchesColumnRule
from .R34_intravilan_area_sum import IntravilanAreaSumRule
from .R35_rlu_codes_preexist import RluCodesPreexistRule
from .R36_zones_code_type_consistency import ZonesCodeTypeConsistencyRule

# ---------------------------------------------------------------------------
# Regula 10: structura fisierului GPKG trebuie sa fie conforma cu sablonul
# publicat (sistem de coordonate, straturi, tipuri de geometrie, campuri,
# tipuri de date).
# ---------------------------------------------------------------------------
register_rule(
    GpkgStructureMatchesTemplateRule(
        rule_id=10,
        name="Structura GPKG conforma cu sablonul",
        description=(
            "Se verifica daca structura fisierului GPKG (sistem de coordonate, "
            "straturi, tipuri de geometrie, campuri, tipuri de date) este conforma "
            "cu sablonul de referinta. Nu se verifica continutul inregistrarilor."
        ),
    )
)

# ---------------------------------------------------------------------------
# Regula 11: corelare (cod, tip) intre ZFPropusa / ZonaReglementareSuplimentara
# si straturile de regulament RLU / RLUD.
# ---------------------------------------------------------------------------
register_rule(
    LayerDataRule(
        rule_id=11,
        name="Verifica existenta datelor in straturile fisierului GPKG",
        description=(
            "Se verifica daca urmatoarele straturi obligatorii contin cel putin o "
            "inregistrare: PlanSpatial, ZFExistenta, ZFPropusa, ZonaReglementareSuplimentara,"
            "RegulamentLocalUrbanism, RegulamentLocalUrbanismDetaliat, LimitaIntravilanExistenta,"
            "LimitaIntravilanPropusa, ReteleTehnicoEdilitare, CaiComunicatie, ReglementariUrbanisticePunct."
        ),
        rules=[
            "PlanSpatial", "ZFExistenta", "ZFPropusa", "ZonaReglementareSuplimentara", "RegulamentLocalUrbanism",
            "RegulamentLocalUrbanismDetaliat", "LimitaIntravilanExistenta", "LimitaIntravilanPropusa",
            "ReteleTehnicoEdilitare", "CaiComunicatie", "ReglementariUrbanisticePunct"
        ]
    )
)

# ---------------------------------------------------------------------------
# Regula 12: coloanele obligatorii ale straturilor trebuie sa contina date.
# ---------------------------------------------------------------------------
register_rule(
    ColumnDataRule(
        rule_id=12,
        name="Coloanele straturilor din GPKG contin date",
        description=(
            "Se verifica daca straturile contin date si daca fiecare coloana "
            "obligatorie nu are valori NULL/lipsa."
        ),
        rules={
            "PlanSpatial": ["SIRUTA", "Judet", "UAT", "NivelPlan", "TitluPlan", "HCL", "Data_aprob", "Data_exp", "ArieADM", "ArieINT", "AriePlan"],
            # Nota: sursa publicata omite complet "ZFPropusa" din acest tabel si repeta
            # "ZFExistenta" ca cheie (cu doua liste diferite de coloane) - probabil o
            # eroare de transcriere pe site. Am corectat: ambele straturi ZF folosesc
            # aceeasi lista de coloane obligatorii (cea mai completa dintre cele doua
            # publicate pentru ZFExistenta).
            "ZFExistenta": ["Cod_ZF", "Cod_SZF", "Tip_SZF", "HILUCS_N1", "Arie_ZF", "Data_exp", "Data_aprob"],
            "ZFPropusa": ["Cod_ZF", "Cod_SZF", "Tip_SZF", "HILUCS_N1", "Arie_ZF", "Data_exp", "Data_aprob"],
            "ZonaReglementareSuplimentara": ["Cod_ZRS", "Cod_ZRS_D", "Tip_ZRS_D", "Arie_ZRS", "Sursa_ZRS", "Detalii_sursa_ZRS", "Data_aprob", "Data_exp"],
            "RegulamentLocalUrbanism": ["Cod_ZF_ZRS", "Tip_zona", "Tip_ZF_ZRS", "Desc_ZF_ZRS"],
            "RegulamentLocalUrbanismDetaliat": ["Tip_zona", "Tip_SZF_ZRS_D", "Desc_SZF_ZRS_D",
                                               # kit 3.0.4+: campul principal SAU cel de detaliu
                                               ("POT", "POT_detaliu"), ("CUT", "CUT_detaliu"),
                                               ("Clad_Hmax", "Clad_Hmax_detaliu")],
            "LimitaIntravilanExistenta": ["SIRUTA", "Judet", "UAT", "Revizie", "Sursa_revizie", "ArieINT"],
            "LimitaIntravilanPropusa": ["SIRUTA", "Judet", "UAT", "Revizie", "ArieINT"],
            "ReteleTehnicoEdilitare": ["Cod_RTE", "Tip_RTE", "Subtip_RTE", "Stadiu_RTE", "Lungime"],
            "CaiComunicatie": ["Tip_CCom", "Subtip_CCom", "Stadiu_CCom", "Lungime"],
            "ReglementariUrbanisticePunct": ["ID_RU", "Tip_RU", "Detaliu_RU"],
        },
    )
)

# ---------------------------------------------------------------------------
# Regula 13: valorile din coloane trebuie sa fie conforme cu OMDLPA 904
# (comparate fata de tabelele de referinta din sablonul GPKG).
# ---------------------------------------------------------------------------
register_rule(
    AllowedValuesRule(
        rule_id=13,
        name="Valori admise (OMDLPA 904)",
        description=(
            "Se verifica daca valorile din coloanele configurate se regasesc in "
            "listele de valori admise, preluate din tabelele de referinta ale "
            "sablonului GPKG."
        ),
        rules={
            "PlanSpatial": [{"columns": ["NivelPlan"], "match": "NivelPlan"}],
            "ZFExistenta": [
                {"columns": ["Cod_ZF"], "match": "Cod_ZF_ZRS"},
                {"columns": ["Tip_ZF"], "match": "Tip_ZF_ZRS"},
                {"columns": ["HILUCS_N1"], "match": "Hilucs"},
            ],
            "ZFPropusa": [
                {"columns": ["Cod_ZF"], "match": "Cod_ZF_ZRS"},
                {"columns": ["Tip_ZF"], "match": "Tip_ZF_ZRS"},
                {"columns": ["HILUCS_N1"], "match": "Hilucs"},
            ],
            # Nota: sursa publicata verifica "Tip_ZRS" (un string de tip, ex. "Zonă
            # funcțională") fata de lista de coduri "Cod_ZF_ZRS" - imposibil de
            # respectat, ar esua mereu. Corectat: primul grup valideaza doar
            # "Cod_ZRS" fata de coduri; "Tip_ZRS" ramane validat doar in al doilea
            # grup, fata de lista de tipuri.
            "ZonaReglementareSuplimentara": [
                {"columns": ["Cod_ZRS"], "match": "Cod_ZF_ZRS"},
                {"columns": ["Tip_ZRS"], "match": "Tip_ZF_ZRS"},
            ],
            # Nota: sursa publicata verifica "Tip_ZF_ZRS" (un string de tip) fata de
            # lista de coduri "Cod_ZF_ZRS" - aceeasi problema ca mai sus, si in plus
            # coloana "Cod_ZF_ZRS" nu era validata deloc. Corectat: primul grup
            # valideaza "Cod_ZF_ZRS" fata de coduri.
            "RegulamentLocalUrbanism": [
                {"columns": ["Cod_ZF_ZRS"], "match": "Cod_ZF_ZRS"},
                {"columns": ["Tip_ZF_ZRS"], "match": "Tip_ZF_ZRS"},
                {"columns": ["Tip_zona"], "match": "TipZona"},
            ],
            "RegulamentLocalUrbanismDetaliat": [
                {"columns": ["Tip_zona"], "match": "TipSubzona"},
            ],
            "ReteleTehnicoEdilitare": [
                {"columns": ["Tip_RTE"], "match": "TipRTE"},
                {"columns": ["Subtip_RTE"], "match": "SubtipRTE"},
                {"columns": ["Stadiu_RTE"], "match": "StadiuRTE"},
            ],
            "CaiComunicatie": [
                {"columns": ["Tip_CCom", "Subtip_CCom"], "match": "TipCCom"},
                {"columns": ["Subtip_CCom"], "match": "SubtipCCom"},
                {"columns": ["Stadiu_CCom"], "match": "StadiuCCom"},
            ],
            "ReglementariUrbanisticePunct": [
                {"columns": ["Tip_RU"], "match": "TipRU"},
            ],
        },
    )
)

# ---------------------------------------------------------------------------
# Regula 14: structura valorilor (regex) conform OMDLPA 904.
# ---------------------------------------------------------------------------
register_rule(
    ValuePatternRule(
        rule_id=14,
        name="Structura valorilor (regex, OMDLPA 904)",
        description=(
            "Se verifica daca valorile din coloanele configurate respecta "
            "expresiile regulate (fullmatch) asociate."
        ),
        rules={
            "PlanSpatial": [
                {"columns": ["HCL"], "match": r"^\d{1,6}$"},
                {"columns": ["Data_aprob", "Data_exp"], "match": r"^\d{4}[-/\.]\d{2}[-/\.]\d{2}$|^\d{2}[-/\.]\d{2}[-/\.]\d{4}$"},
                {"columns": ["ArieADM", "ArieINT", "AriePlan"], "match": r"^\d*\.\d{1,2}$"},
            ],
            "ZFExistenta": [
                {"columns": ["Arie_ZF"], "match": r"^\d*\.\d{1,2}$"},
                {"columns": ["Data_exp"], "match": r"^\d{4}[-/\.]\d{2}[-/\.]\d{2}$|^\d{2}[-/\.]\d{2}[-/\.]\d{4}$"},
            ],
            "ZFPropusa": [
                {"columns": ["Arie_ZF"], "match": r"^\d*\.\d{1,2}$"},
                {"columns": ["Data_aprob", "Data_exp"], "match": r"^\d{4}[-/\.]\d{2}[-/\.]\d{2}$|^\d{2}[-/\.]\d{2}[-/\.]\d{4}$"},
            ],
            "ZonaReglementareSuplimentara": [
                {"columns": ["Arie_ZRS"], "match": r"^\d*\.\d{1,2}$"},
                {"columns": ["Data_aprob", "Data_exp"], "match": r"^\d{4}[-/\.]\d{2}[-/\.]\d{2}$|^\d{2}[-/\.]\d{2}[-/\.]\d{4}$"},
            ],
            "LimitaIntravilanExistenta": [
                {"columns": ["Revizie"], "match": r"^\d{4}[-/\.]\d{2}[-/\.]\d{2}$|^\d{2}[-/\.]\d{2}[-/\.]\d{4}$"},
                {"columns": ["Sursa_revizie"], "match": r"^\d{1,6}\/(0[1-9]|[1-2][0-9]|3[0-1])\.(0[1-9]|1[0-2])\.\d{4}$"},
                {"columns": ["ArieINT"], "match": r"^\d*\.\d{1,2}$"},
            ],
            "LimitaIntravilanPropusa": [
                {"columns": ["Revizie"], "match": r"^\d{4}[-/\.]\d{2}[-/\.]\d{2}$|^\d{2}[-/\.]\d{2}[-/\.]\d{4}$"},
                {"columns": ["ArieINT"], "match": r"^\d*\.\d{1,2}$"},
            ],
            "ReteleTehnicoEdilitare": [
                {"columns": ["Lungime"], "match": r"^\d*\.\d{1,2}$"},
            ],
            "CaiComunicatie": [
                {"columns": ["Lungime"], "match": r"^\d*\.\d{1,2}$"},
            ],
        },
    )
)

# ---------------------------------------------------------------------------
# Regula 15: coloane de date temporale corecte cronologic fata de data curenta.
# ---------------------------------------------------------------------------
register_rule(
    TemporalValidityRule(
        rule_id=15,
        name="Validitate cronologica a coloanelor de data",
        description=(
            "Se verifica daca datele din coloanele de tip aprobare/expirare/"
            "revizie sunt prezente, valide si (pentru aprobare/revizie) nu sunt "
            "ulterioare datei curente."
        ),
        rules={
            "PlanSpatial": {"aprob": "Data_aprob", "exp": "Data_exp"},
            "ZFPropusa": {"exp": "Data_exp"},
            "ZonaReglementareSuplimentara": {"aprob": "Data_aprob", "exp": "Data_exp"},
            "LimitaIntravilanExistenta": {"revizie": "Revizie"},
            "LimitaIntravilanPropusa": {"revizie": "Revizie"},
        },
    )
)

# ---------------------------------------------------------------------------
# Regula 16: corelare ierarhica HILUCS_N1/N2/N3.
# ---------------------------------------------------------------------------
register_rule(
    HilucsHierarchyRule(
        rule_id=16,
        name="Corelare ierarhica HILUCS",
        description=(
            "Se verifica daca HILUCS_N1, HILUCS_N2 si HILUCS_N3 sunt coduri "
            "valide si daca respecta ierarhia parinte-copil din tabelul de "
            "referinta HILUCS."
        ),
        rules={
            "ZFExistenta": ["HILUCS_N1", "HILUCS_N2", "HILUCS_N3"],
            "ZFPropusa": ["HILUCS_N1", "HILUCS_N2", "HILUCS_N3"],
        },
    )
)

# ---------------------------------------------------------------------------
# Regula 17: unicitate cod/tip in RLU si RLUD.
# ---------------------------------------------------------------------------
register_rule(
    UniqueValuesRule(
        rule_id=17,
        name="Unicitate cod/tip (RLU, RLUD)",
        description="Se verifica daca valorile din coloanele configurate sunt unice in cadrul stratului.",
        rules={
            "RegulamentLocalUrbanism": ["Cod_ZF_ZRS", "Tip_ZF_ZRS"],
            # Nota: sursa publicata foloseste "Cod_ZF_ZRS_D"/"Tip_ZF_ZRS_D", care nu
            # exista in schema acestui strat (campurile reale sunt "Cod_SZF_ZRS_D"/
            # "Tip_SZF_ZRS_D", ca in R19/R22) - corectat mai jos.
            "RegulamentLocalUrbanismDetaliat": ["Cod_SZF_ZRS_D", "Tip_SZF_ZRS_D"],
        },
    )
)

# ---------------------------------------------------------------------------
# Regula 18: consistenta datelor temporale in zonele functionale.
# ---------------------------------------------------------------------------
register_rule(
    ConsistentTemporalRule(
        rule_id=18,
        name="Consistenta datelor temporale (ZF)",
        description=(
            "Se verifica daca toate inregistrarile dintr-o coloana de data au "
            "aceeasi valoare la nivelul intregului strat."
        ),
        rules={
            "ZFExistenta": ["Data_aprob", "Data_exp"],
            "ZFPropusa": ["Data_aprob", "Data_exp"],
        },
    )
)

# ---------------------------------------------------------------------------
# Regula 19: corelare (cod, tip) intre ZFPropusa / ZonaReglementareSuplimentara
# si straturile de regulament RLU / RLUD.
# ---------------------------------------------------------------------------
register_rule(
    ReferenceCorrelationRule(
        rule_id=19,
        name="Corelare ZF/ZRS cu regulament (RLU/RLUD)",
        description=(
            "Verifica perechile (cod, tip) din ZFPropusa si "
            "ZonaReglementareSuplimentara fata de RegulamentLocalUrbanism si "
            "RegulamentLocalUrbanismDetaliat."
        ),
        rules=[
            {
                "layer": "RegulamentLocalUrbanism",
                "matches_fields_from": {"ZFPropusa": ["Cod_ZF", "Tip_ZF"]},
                "validated_fields": ["Cod_ZF_ZRS", "Tip_ZF_ZRS"],
            },
            {
                "layer": "RegulamentLocalUrbanism",
                "matches_fields_from": {
                    "ZonaReglementareSuplimentara": ["Cod_ZRS", "Tip_ZRS"]
                },
                "validated_fields": ["Cod_ZF_ZRS", "Tip_ZF_ZRS"],
            },
            {
                "layer": "RegulamentLocalUrbanismDetaliat",
                "matches_fields_from": {
                    "ZonaReglementareSuplimentara": ["Cod_ZRS_D", "Tip_ZRS_D"]
                },
                "validated_fields": ["Cod_SZF_ZRS_D", "Tip_SZF_ZRS_D"],
            },
            {
                "layer": "RegulamentLocalUrbanismDetaliat",
                "matches_fields_from": {"ZFPropusa": ["Cod_SZF", "Tip_SZF"]},
                "validated_fields": ["Cod_SZF_ZRS_D", "Tip_SZF_ZRS_D"],
            },
        ],
    )
)

# ---------------------------------------------------------------------------
# Regula 20: datele temporale din PlanSpatial coincid cu ZF/ZRS.
# ---------------------------------------------------------------------------
register_rule(
    PlanSpatialTemporalMatchRule(
        rule_id=20,
        name="Corelare temporala PlanSpatial - ZF/ZRS",
        description=(
            "Se verifica daca Data_aprob/Data_exp din ZFPropusa si "
            "ZonaReglementareSuplimentara coincid cu cele din PlanSpatial."
        ),
        rules=[
            {"layer": "PlanSpatial", "match_fields_from": {"ZFPropusa": "Data_aprob"}, "with_field": "Data_aprob"},
            {"layer": "PlanSpatial", "match_fields_from": {"ZFPropusa": "Data_exp"}, "with_field": "Data_exp"},
            {"layer": "PlanSpatial", "match_fields_from": {"ZonaReglementareSuplimentara": "Data_aprob"}, "with_field": "Data_aprob"},
            {"layer": "PlanSpatial", "match_fields_from": {"ZonaReglementareSuplimentara": "Data_exp"}, "with_field": "Data_exp"},
        ],
    )
)

# ---------------------------------------------------------------------------
# Regula 21: perioadele ZFPropusa nu se suprapun cu ZFExistenta si sunt cronologice.
# ---------------------------------------------------------------------------
register_rule(
    ZFPeriodOverlapRule(
        rule_id=21,
        name="Perioade ZF fara suprapunere si cronologice",
        description=(
            "Se verifica daca intervalele [Data_aprob, Data_exp] din ZFPropusa "
            "sunt cronologice si nu se suprapun cu intervalele din ZFExistenta."
        ),
        rules={
            "ZFPropusa": {
                "match_fields_from": {"ZFExistenta": ["Data_aprob", "Data_exp"]},
                "with_field": ["Data_aprob", "Data_exp"],
            }
        },
    )
)

# ---------------------------------------------------------------------------
# Regula 22: perechile cod/tip din RLUD trebuie sa provina din ZF/ZRS.
# ---------------------------------------------------------------------------
register_rule(
    PairMembershipRule(
        rule_id=22,
        name="Perechi cod/tip regulament valide fata de ZF/ZRS",
        description=(
            "Se verifica daca perechile (cod, tip) din RegulamentLocalUrbanism si "
            "RegulamentLocalUrbanismDetaliat se regasesc in ZFPropusa sau "
            "ZonaReglementareSuplimentara."
        ),
        rules=[
            {
                "validated_layer": "RegulamentLocalUrbanismDetaliat",
                "validated_fields": ["Cod_SZF_ZRS_D", "Tip_SZF_ZRS_D"],
                "valid_pairs_from": [
                    {"layer": "ZFPropusa", "fields": ["Cod_SZF", "Tip_SZF"]},
                    {"layer": "ZonaReglementareSuplimentara", "fields": ["Cod_ZRS_D", "Tip_ZRS_D"]},
                ],
            },
            {
                "validated_layer": "RegulamentLocalUrbanism",
                "validated_fields": ["Cod_ZF_ZRS", "Tip_ZF_ZRS"],
                "valid_pairs_from": [
                    {"layer": "ZFPropusa", "fields": ["Cod_ZF", "Tip_ZF"]},
                    {"layer": "ZonaReglementareSuplimentara", "fields": ["Cod_ZRS", "Tip_ZRS"]},
                ],
            },
        ],
    )
)

# ---------------------------------------------------------------------------
# Regula 23: SIRUTA din LimitaIntravilan* trebuie sa fie subordonata SIRUTA din PlanSpatial.
# ---------------------------------------------------------------------------
register_rule(
    SirutaHierarchyRule(
        rule_id=23,
        name="Ierarhie SIRUTA (PlanSpatial - LimitaIntravilan)",
        description=(
            "Se verifica daca SIRUTA din LimitaIntravilanExistenta/Propusa este "
            "subordonata codului SIRUTA din PlanSpatial, folosind ierarhia SIRUTA "
            "din sablonul GPKG."
        ),
        rules={
            "source_layer": "PlanSpatial",
            "source_fields": ["SIRUTA", "Judet", "UAT"],
            "validated_layers": [
                {"layer": "LimitaIntravilanPropusa", "fields": ["SIRUTA", "Judet", "UAT"]},
                {"layer": "LimitaIntravilanExistenta", "fields": ["SIRUTA", "Judet", "UAT"]},
            ],
        },
    )
)

# ---------------------------------------------------------------------------
# Regula 24: geometriile trebuie sa existe (non-NULL).
# ---------------------------------------------------------------------------
register_rule(
    GeometryExistsRule(
        rule_id=24,
        name="Geometrii prezente (non-NULL)",
        description="Se verifica daca geometriile straturilor exista si nu sunt NULL.",
        valoare_regula=(
            "PlanSpatial,ZFExistenta,ZFPropusa,ZonaReglementareSuplimentara,"
            "LimitaIntravilanExistenta,LimitaIntravilanPropusa,ReteleTehnicoEdilitare,"
            "CaiComunicatie,ReglementariUrbanisticePunct"
        ),
    )
)

# ---------------------------------------------------------------------------
# Regula 25: geometriile trebuie sa fie valide (GEOS IsValid()).
# ---------------------------------------------------------------------------
register_rule(
    GeometryValidRule(
        rule_id=25,
        name="Geometrii valide (GEOS)",
        description="Se verifica daca geometriile straturilor sunt valide din punct de vedere topologic.",
        valoare_regula=(
            "PlanSpatial,ZFExistenta,ZFPropusa,ZonaReglementareSuplimentara,"
            "LimitaIntravilanExistenta,LimitaIntravilanPropusa,ReteleTehnicoEdilitare,"
            "CaiComunicatie,ReglementariUrbanisticePunct"
        ),
    )
)

# ---------------------------------------------------------------------------
# Regula 26: PlanSpatial trebuie sa fie in limita administrativa a UAT.
#
# Nota: foloseste stratul de referinta "~REF_UAT" (o singura entitate, UAT-ul
# curent) deja preluat dinamic in proiect la crearea acestuia, in loc de un
# apel catre un serviciu extern in timpul validarii (vezi tools/uat_boundary.py
# si R26_planspatial_within_uat.py).
# ---------------------------------------------------------------------------
register_rule(
    PlanSpatialWithinUatRule(
        rule_id=26,
        name="PlanSpatial in limita administrativa UAT",
        description=(
            "Se verifica daca geometriile din PlanSpatial se afla in interiorul "
            "limitei administrative a UAT-ului corespunzator codului SIRUTA "
            "(toleranta 0.1 m)."
        ),
        valoare_regula="SIRUTA",
    )
)

# ---------------------------------------------------------------------------
# Regula 27: geometriile straturilor trebuie sa fie in limita PlanSpatial.
# ---------------------------------------------------------------------------
register_rule(
    GeometryWithinPlanSpatialRule(
        rule_id=27,
        name="Geometrii in limita PlanSpatial",
        description=(
            "Se verifica daca geometriile straturilor configurate se afla in "
            "limita stratului PlanSpatial (toleranta 0.1 m)."
        ),
        valoare_regula=(
            "ZFExistenta,ZFPropusa,ZonaReglementareSuplimentara,LimitaIntravilanExistenta,"
            "LimitaIntravilanPropusa,ReteleTehnicoEdilitare,CaiComunicatie,ReglementariUrbanisticePunct"
        ),
    )
)

# ---------------------------------------------------------------------------
# Regula 28: zonele functionale trebuie sa acopere PlanSpatial (arie totala).
# ---------------------------------------------------------------------------
register_rule(
    ZFCoversPlanSpatialRule(
        rule_id=28,
        name="Acoperire PlanSpatial de catre zonele functionale",
        description=(
            "Se verifica daca aria totala a ZFExistenta/ZFPropusa corespunde ariei "
            "totale din PlanSpatial (toleranta 50 mp)."
        ),
        valoare_regula="ZFExistenta,ZFPropusa",
    )
)

# ---------------------------------------------------------------------------
# Regula 29: geometriile din zonele functionale nu trebuie sa se suprapuna.
# ---------------------------------------------------------------------------
register_rule(
    ZFOverlapRule(
        rule_id=29,
        name="Fara suprapuneri in zonele functionale",
        description=(
            "Se detecteaza perechi de geometrii care se suprapun (dupa erodare "
            "cu -0.1 m, pentru a ignora limitele comune) in ZFExistenta si ZFPropusa."
        ),
        valoare_regula="ZFExistenta,ZFPropusa",
    )
)


# ---------------------------------------------------------------------------
# Regula 30: detectie sliver polygons in ZFExistenta si ZFPropusa.
# ---------------------------------------------------------------------------
_r30 = SliverPolygonRule(
    rule_id=30,
    name="Sliver polygons (ZFExistenta, ZFPropusa)",
    description=(
        "Detecteaza poligoane degenerate (arie minima, raport de aspect, "
        "compactitate) in straturile ZFExistenta si ZFPropusa."
    ),
    valoare_regula="ZFExistenta,ZFPropusa",
)
_r30.severity = "WARNING"  # singura regula WARNING dintre cele implementate (11-34)
register_rule(_r30)

# ---------------------------------------------------------------------------
# Regula 31: geometriile trebuie sa fie strict 2D (fara Z/M).
# ---------------------------------------------------------------------------
register_rule(
    Geometry2DRule(
        rule_id=31,
        name="Geometrii strict 2D",
        description="Se verifica daca geometriile nu contin coordonate de altitudine (Z) sau masura (M).",
        valoare_regula=(
            "PlanSpatial,ZFExistenta,ZFPropusa,ZonaReglementareSuplimentara,"
            "LimitaIntravilanExistenta,LimitaIntravilanPropusa,ReteleTehnicoEdilitare,"
            "CaiComunicatie,ReglementariUrbanisticePunct"
        ),
    )
)

# ---------------------------------------------------------------------------
# Regula 32: aria geometrica trebuie sa corespunda coloanei de arie.
# ---------------------------------------------------------------------------
register_rule(
    AreaMatchesColumnRule(
        rule_id=32,
        name="Arie geometrica = coloana de arie",
        description=(
            "Se verifica daca aria calculata a geometriei corespunde valorii "
            "stocate in coloana de arie (ha pentru PlanSpatial/LimitaIntravilan*, "
            "mp pentru ZFExistenta/ZonaReglementareSuplimentara; toleranta 0.1)."
        ),
        rules={
            "PlanSpatial": "AriePlan",
            "ZFExistenta": "Arie_ZF",
            "ZonaReglementareSuplimentara": "Arie_ZRS",
            "LimitaIntravilanExistenta": "ArieINT",
            "LimitaIntravilanPropusa": "ArieINT",
        },
    )
)

# ---------------------------------------------------------------------------
# Regula 33: lungimea geometrica trebuie sa corespunda coloanei Lungime.
# ---------------------------------------------------------------------------
register_rule(
    LengthMatchesColumnRule(
        rule_id=33,
        name="Lungime geometrica = coloana Lungime",
        description=(
            "Se verifica daca lungimea calculata a geometriei corespunde valorii "
            "stocate in coloana Lungime (toleranta 0.1 m)."
        ),
        rules={
            "ReteleTehnicoEdilitare": "Lungime",
            "CaiComunicatie": "Lungime",
        },
    )
)

# ---------------------------------------------------------------------------
# Regula 34: suma ArieINT din LimitaIntravilanPropusa = ArieINT din PlanSpatial.
# ---------------------------------------------------------------------------
register_rule(
    IntravilanAreaSumRule(
        rule_id=34,
        name="Suma ArieINT LimitaIntravilanPropusa = ArieINT PlanSpatial",
        description=(
            "Se verifica daca suma coloanei ArieINT din LimitaIntravilanPropusa "
            "este egala cu ArieINT din PlanSpatial (toleranta 0.1 ha)."
        ),
        rules={
            "PlanSpatial": "ArieINT",
            "LimitaIntravilanPropusa": "ArieINT",
        },
    )
)

# ---------------------------------------------------------------------------
# Regula 35 (extindere, fara "Nr." public - vezi R35_rlu_codes_preexist.py):
# codurile din RegulamentLocalUrbanism trebuie sa preexiste in ZFPropusa/
# ZonaReglementareSuplimentara.
# ---------------------------------------------------------------------------
register_rule(
    RluCodesPreexistRule(
        rule_id=35,
        name="Codurile RegulamentLocalUrbanism preexista in ZF/ZRS",
        description=(
            "Se verifica daca fiecare Cod_ZF_ZRS din RegulamentLocalUrbanism exista "
            "deja ca Cod_ZF in ZFPropusa sau ca Cod_ZRS in ZonaReglementareSuplimentara "
            "(extindere gasita prin audit al validatorului oficial, fara numar public)."
        ),
    )
)

# ---------------------------------------------------------------------------
# Regula 36 (extindere, fara "Nr." public - vezi R36_zones_code_type_consistency.py):
# consistenta cod->tip in interiorul aceluiasi strat, pentru familia de
# straturi zona/subzona.
# ---------------------------------------------------------------------------
register_rule(
    ZonesCodeTypeConsistencyRule(
        rule_id=36,
        name="Consistenta cod-tip in acelasi strat (zone)",
        description=(
            "Se verifica daca aceeasi valoare de cod nu apare niciodata cu doua "
            "valori de tip diferite in acelasi strat (extindere gasita prin audit "
            "al validatorului oficial, fara numar public)."
        ),
        valoare_regula={
            "ZFExistenta": [("Cod_ZF", "Tip_ZF"), ("Cod_SZF", "Tip_SZF")],
            "ZFPropusa": [("Cod_ZF", "Tip_ZF"), ("Cod_SZF", "Tip_SZF")],
            "ZonaReglementareSuplimentara": [("Cod_ZRS", "Tip_ZRS"), ("Cod_ZRS_D", "Tip_ZRS_D")],
            "RegulamentLocalUrbanism": [("Cod_ZF_ZRS", "Tip_ZF_ZRS")],
            "RegulamentLocalUrbanismDetaliat": [("Cod_SZF_ZRS_D", "Tip_SZF_ZRS_D")],
        },
    )
)
