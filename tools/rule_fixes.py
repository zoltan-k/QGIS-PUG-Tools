# -*- coding: utf-8 -*-
"""
Fixuri "un buton" pentru un subset de reguli de validare - NUMAI la cererea
explicita a utilizatorului, dintr-un buton in dialogul de rezultate ale
validarii (vezi ui/results_dialog.py). NU sunt niciodata aplicate automat -
nici la actualizarea pachetului (tools/package_updater.py), nici in alt flux.

O regula e "fixabila" aici doar daca exista o singura valoare corecta,
lipsita de ambiguitate, derivabila direct din alte date deja prezente si de
incredere (geometrie -> arie/lungime, plan spatial -> zone functionale) -
NU si atunci cand "valoarea corecta" ar necesita o decizie editoriala (ex.
care dintre doua valori introduse manual e cea gresita). Setul acoperit:
R31 (geometrie stricta 2D), R32 (arie), R33 (lungime), R34 (suma ariilor
intravilan), R26 (PlanSpatial in limita UAT), R27 (geometrii in limita
PlanSpatial), si un fix combinat pentru R18+R20+R21 (corelare temporala).

Fiecare fix modifica DIRECT straturile deja incarcate in proiectul QGIS activ
(edit buffer + commit imediat pe fiecare strat atins, fara sesiune de
editare lasata deschisa), ca schimbarile sa fie vizibile imediat pe canvas
si sa foloseasca exact aceleasi straturi pe care utilizatorul le vede in
rezultatele validarii - nu SQL brut pe fisierul GPKG (spre deosebire de
package_updater.py, care opereaza pe un proiect inchis).
"""

from contextlib import contextmanager
from datetime import date, timedelta

from qgis.core import QgsDefaultValue

from ..validations.gpkg_utils import get_layer, is_null, parse_date
from ..validations.R26_planspatial_within_uat import (
    BOUNDARY_LAYER,
    BOUNDARY_SIRUTA_FIELD,
    BUFFER_SEGMENTS,
)
from ..validations.R26_planspatial_within_uat import STRICT_TOLERANCE as R26_STRICT_TOLERANCE
from ..validations.R27_geometry_within_planspatial import REFERENCE_LAYER
from ..validations.R27_geometry_within_planspatial import STRICT_TOLERANCE as R27_STRICT_TOLERANCE
from ..validations.R32_area_matches_column import HECTARE_LAYERS
from ..validations.R32_area_matches_column import TOLERANCE as AREA_TOLERANCE
from ..validations.R33_length_matches_column import TOLERANCE as LENGTH_TOLERANCE

TEMPORAL_REDATE_RULE_IDS = (18, 20, 21)


@contextmanager
def _suppress_default_values(layer):
    """
    Dezactiveaza temporar valoarea implicita (si applyOnUpdate) pentru
    TOATE campurile stratului, pe obiectul de strat DEJA INCARCAT, cat timp fix-ul
    scrie explicit o valoare intr-un camp - fara aceasta, un camp cu
    applyOnUpdate=True (vezi layer_styles) isi re-evalueaza propria
    expresie IMEDIAT dupa commitChanges(), suprascriind valoarea corect
    calculata de fix cu orice calculeaza acea expresie. Confirmat empiric
    pe un proiect legacy: "ZFExistenta.Arie_ZF" avea o expresie implicita
    gresita (inmultea aria cu 10 - acelasi bug gasit si corectat anterior
    pentru "ZFPropusa.Arie_ZF", dar nepropagat inca in acest proiect prin
    "Actualizeaza pachetul"), care anula complet incercarea acestui fix de
    a scrie valoarea corecta - fix-ul raporta succes (commitChanges()
    reusea), dar valoarea de pe disc ramanea cea gresita.

    IMPORTANT, confirmat tot empiric: applyOnUpdate al UNUI camp se
    reevalueaza la COMMIT-ul oricarei modificari a feature-ului, nu doar
    cand ACEL camp anume e cel editat - un fix ULTERIOR care modifica alt
    camp de pe acelasi strat (ex. fix_temporal_redate schimband
    Data_aprob/Data_exp) poate re-strica un camp DEJA reparat de un fix
    ANTERIOR (ex. Arie_ZF, reparat de fix_area_column) daca acel camp are
    propriul applyOnUpdate si nu e SI el suprimat. De aceea se suprima
    intotdeauna TOATE campurile stratului, nu doar cele explicit scrise.

    NU modifica stilul salvat (QML/layer_styles) - doar comportamentul
    obiectului de strat deja incarcat, pentru durata editarii, restaurat
    imediat dupa (indiferent daca editarea reuseste sau nu).
    """
    all_indices = range(layer.fields().count())
    originals = {idx: layer.defaultValueDefinition(idx) for idx in all_indices}
    for idx in all_indices:
        layer.setDefaultValueDefinition(idx, QgsDefaultValue())
    try:
        yield
    finally:
        for idx, original in originals.items():
            layer.setDefaultValueDefinition(idx, original)


class FixResult:
    """Rezumatul unei operatii de fix, afisat utilizatorului dupa aplicare."""

    def __init__(self):
        self.changed = 0
        self.skipped = 0
        self.notes = []

    def note(self, text):
        self.notes.append(text)

    def summary(self):
        text = f"Modificari aplicate: {self.changed}."
        if self.skipped:
            text += f" Ignorate (fara geometrie/date de referinta): {self.skipped}."
        if self.notes:
            text += "\n\n" + "\n".join(self.notes)
        return text


def _year_shift(d, years):
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        # 29 februarie intr-un an care devine ne-bisect
        return d.replace(month=2, day=28, year=d.year + years)


def _clip_geometry(geom, target_geom, strict_tolerance, buffer_segments=8):
    """
    Intersecteaza geom cu target_geom, dar NUMAI daca geom nu se afla deja in
    interiorul lui target_geom cu toleranta STRICTA folosita si de regula de
    validare corespunzatoare (nu bufferul extins configurabil - o geometrie
    care trece deja regula, chiar daca nu perfect exact, nu trebuie atinsa).
    Rezultatul e normalizat strict 2D (o intersectie GEOS nu ar trebui sa
    introduca Z/M, dar normalizarea e ieftina si elimina orice ambiguitate).

    Returneaza None daca geom nu are nevoie de nicio modificare, sau
    tuplul (geometrie_noua, era_goala) daca s-a incercat clip-ul.
    """
    strict_geom = target_geom.buffer(strict_tolerance, buffer_segments)
    if geom.within(strict_geom):
        return None
    clipped = geom.intersection(target_geom)
    if clipped is None or clipped.isEmpty():
        return clipped, True
    abstract = clipped.get()
    if abstract.is3D():
        abstract.dropZValue()
    if abstract.isMeasure():
        abstract.dropMValue()
    return clipped, False


def _commit_geometry_updates(result, layer, updates):
    if not updates:
        return
    if not layer.startEditing():
        result.note(f"'{layer.name()}': nu s-a putut porni editarea.")
        return
    for fid, geom in updates.items():
        layer.changeGeometry(fid, geom)
    if layer.commitChanges():
        result.changed += len(updates)
    else:
        result.note(f"'{layer.name()}': commitChanges() a esuat - {layer.commitErrors()}")
        layer.rollBack()


def _reset_gpkg_geometry_z_m_flags(layer, result):
    """
    GDAL "largeste" automat declaratia de tip a coloanei de geometrie
    ("gpkg_geometry_columns".z/m, 0=interzis / 1=obligatoriu / 2=optional) in
    momentul in care e scrisa o geometrie cu Z sau M - o data largita, ramane
    asa chiar daca ulterior NICIO geometrie din tabela nu mai are Z/M (ex.
    dupa fix_geometry_2d). Regula 10 (structura GPKG conforma cu sablonul)
    compara aceasta declaratie de tip (nu geometriile individuale), asa ca
    fara acest pas fix_geometry_2d ar "repara" R31 dar ar lasa in urma un
    esec nou la R10. Se reseteaza direct prin SQL (QGIS/OGR nu expune
    modificarea declaratiei de tip a unei coloane existente prin API-ul de
    editare a straturilor) - doar la 0, niciodata la un tip mai permisiv.
    """
    import sqlite3

    source = layer.source().split("|")[0]
    if not source.lower().endswith(".gpkg"):
        return
    table_name = layer.name()
    con = sqlite3.connect(source)
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT z, m FROM gpkg_geometry_columns WHERE table_name = ?", (table_name,)
        )
        row = cur.fetchone()
        if row is None or (row[0] == 0 and row[1] == 0):
            return
        cur.execute(
            "UPDATE gpkg_geometry_columns SET z = 0, m = 0 WHERE table_name = ?",
            (table_name,),
        )
        con.commit()
    except sqlite3.DatabaseError as exc:
        result.note(f"'{table_name}': nu s-a putut reseta declaratia Z/M din gpkg_geometry_columns - {exc}")
    finally:
        con.close()


# -- R31: geometrie stricta 2D (elimina coordonatele Z/M) ---------------------

def fix_geometry_2d(project, rule):
    result = FixResult()
    for layer_name in rule.layer_names:
        try:
            layer = get_layer(project, layer_name)
        except ValueError as exc:
            result.note(str(exc))
            continue

        updates = {}
        for feat in layer.getFeatures():
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                result.skipped += 1
                continue
            abstract = geom.get()
            changed = False
            if abstract.is3D():
                abstract.dropZValue()
                changed = True
            if abstract.isMeasure():
                abstract.dropMValue()
                changed = True
            if changed:
                updates[feat.id()] = geom

        if updates:
            changed_before = result.changed
            _commit_geometry_updates(result, layer, updates)
            if result.changed > changed_before:
                _reset_gpkg_geometry_z_m_flags(layer, result)
    return result


# -- R32/R33: arie/lungime recalculate din geometrie ---------------------------

def _fix_computed_column(project, rule, compute, tolerance):
    result = FixResult()
    for layer_name, field_name in rule.rules.items():
        try:
            layer = get_layer(project, layer_name)
        except ValueError as exc:
            result.note(str(exc))
            continue

        field_index = layer.fields().indexOf(field_name)
        if field_index < 0:
            result.note(f"'{layer_name}': coloana '{field_name}' nu exista.")
            continue

        updates = {}
        for feat in layer.getFeatures():
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                result.skipped += 1
                continue
            computed = compute(geom, layer_name)
            stored = feat[field_name]
            if is_null(stored) or abs(computed - float(stored)) > tolerance:
                updates[feat.id()] = computed

        if not updates:
            continue
        if not layer.startEditing():
            result.note(f"'{layer_name}': nu s-a putut porni editarea.")
            continue
        with _suppress_default_values(layer):
            for fid, value in updates.items():
                layer.changeAttributeValue(fid, field_index, value)
            if layer.commitChanges():
                result.changed += len(updates)
            else:
                result.note(f"'{layer_name}': commitChanges() a esuat - {layer.commitErrors()}")
                layer.rollBack()
    return result


def fix_area_column(project, rule):
    def compute(geom, layer_name):
        divisor = 10000.0 if layer_name in HECTARE_LAYERS else 1.0
        return round(geom.area() / divisor, 2)

    return _fix_computed_column(project, rule, compute, AREA_TOLERANCE)


def fix_length_column(project, rule):
    def compute(geom, layer_name):
        return round(geom.length(), 2)

    return _fix_computed_column(project, rule, compute, LENGTH_TOLERANCE)


# -- R34: suma ariilor LimitaIntravilanPropusa suprascrie PlanSpatial.ArieINT --

def fix_intravilan_area_sum(project, rule):
    """
    Geometria din LimitaIntravilanPropusa e sursa de adevar (nu coloana ei de
    arie, care poate fi ea insasi gresita - vezi R32): aria fiecarei entitati
    se recalculeaza direct din geometrie, iar suma (in hectare) suprascrie
    PlanSpatial.ArieINT, indiferent de valoarea ei curenta.
    """
    result = FixResult()
    try:
        ps_layer = get_layer(project, rule.planspatial_layer_name)
        propusa_layer = get_layer(project, rule.propusa_layer_name)
    except ValueError as exc:
        result.note(str(exc))
        return result

    if ps_layer.featureCount() != 1:
        result.note(
            f"'{rule.planspatial_layer_name}' trebuie sa contina exact o "
            f"singura entitate (are {ps_layer.featureCount()})."
        )
        return result

    total_m2 = 0.0
    for feat in propusa_layer.getFeatures():
        geom = feat.geometry()
        if geom is None or geom.isEmpty():
            result.skipped += 1
            continue
        total_m2 += geom.area()
    total_ha = round(total_m2 / 10000.0, 2)

    field_index = ps_layer.fields().indexOf(rule.planspatial_field)
    if field_index < 0:
        result.note(
            f"'{rule.planspatial_layer_name}': coloana '{rule.planspatial_field}' nu exista."
        )
        return result

    ps_feat = next(ps_layer.getFeatures())
    if not ps_layer.startEditing():
        result.note(f"'{rule.planspatial_layer_name}': nu s-a putut porni editarea.")
        return result
    with _suppress_default_values(ps_layer):
        ps_layer.changeAttributeValue(ps_feat.id(), field_index, total_ha)
        if ps_layer.commitChanges():
            result.changed = 1
        else:
            result.note(f"'{rule.planspatial_layer_name}': commitChanges() a esuat - {ps_layer.commitErrors()}")
            ps_layer.rollBack()
    return result


# -- R26: clip PlanSpatial la limita ~REF_UAT ----------------------------------

def fix_clip_planspatial_to_uat(project, rule):
    result = FixResult()
    try:
        layer = get_layer(project, rule.layer_name)
        boundary_layer = get_layer(project, BOUNDARY_LAYER)
    except ValueError as exc:
        result.note(str(exc))
        return result

    siruta_values = set()
    for feat in layer.getFeatures():
        code = rule._as_int(feat[rule.siruta_field])
        if code is not None:
            siruta_values.add(code)
    if len(siruta_values) != 1:
        result.note(
            f"'{rule.layer_name}' trebuie sa aiba exact o valoare SIRUTA unica "
            f"(are {len(siruta_values)})."
        )
        return result
    siruta_value = next(iter(siruta_values))

    uat_geom = None
    for feat in boundary_layer.getFeatures():
        if rule._as_int(feat[BOUNDARY_SIRUTA_FIELD]) == siruta_value:
            uat_geom = feat.geometry()
            break
    if uat_geom is None or uat_geom.isEmpty():
        result.note(f"Nu s-a gasit limita UAT pentru SIRUTA {siruta_value}.")
        return result

    updates = {}
    for feat in layer.getFeatures():
        geom = feat.geometry()
        if geom is None or geom.isEmpty():
            result.skipped += 1
            continue
        outcome = _clip_geometry(geom, uat_geom, R26_STRICT_TOLERANCE, BUFFER_SEGMENTS)
        if outcome is None:
            continue
        clipped, was_empty = outcome
        if was_empty:
            result.note(f"FID {feat.id()}: intersectia cu limita UAT e goala - neschimbat.")
            continue
        updates[feat.id()] = clipped

    _commit_geometry_updates(result, layer, updates)
    return result


# -- R27: clip straturile afectate la limita PlanSpatial -----------------------

def fix_clip_to_planspatial(project, rule):
    result = FixResult()
    try:
        ps_layer = get_layer(project, REFERENCE_LAYER)
    except ValueError as exc:
        result.note(str(exc))
        return result

    union_geom = None
    for feat in ps_layer.getFeatures():
        geom = feat.geometry()
        if geom is None or geom.isEmpty():
            continue
        union_geom = geom if union_geom is None else union_geom.combine(geom)
    if union_geom is None or union_geom.isEmpty():
        result.note(f"'{REFERENCE_LAYER}' nu are geometrii valide.")
        return result

    for layer_name in rule.layer_names:
        try:
            layer = get_layer(project, layer_name)
        except ValueError as exc:
            result.note(str(exc))
            continue

        updates = {}
        for feat in layer.getFeatures():
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                result.skipped += 1
                continue
            outcome = _clip_geometry(geom, union_geom, R27_STRICT_TOLERANCE)
            if outcome is None:
                continue
            clipped, was_empty = outcome
            if was_empty:
                result.note(
                    f"'{layer_name}' FID {feat.id()}: intersectia cu "
                    f"'{REFERENCE_LAYER}' e goala - neschimbat."
                )
                continue
            updates[feat.id()] = clipped

        _commit_geometry_updates(result, layer, updates)
    return result


# -- R18+R20+R21: recorelare temporala -----------------------------------------

def fix_temporal_redate(project):
    """
    Fix combinat, tinta unica pentru R18 (consistenta in strat), R20
    (corelare cu PlanSpatial) si R21 (cronologie/suprapunere ZFExistenta vs
    ZFPropusa) - cele trei reguli verifica fatete diferite ale ACELUIASI set
    de date temporale, iar o singura rescriere coerenta le satisface pe toate
    trei simultan (nu are sens sa fie fixate separat).

    Algoritm (PlanSpatial e referinta):
        1. PlanSpatial.Data_aprob: daca lipseste sau e in viitor, devine ieri.
        2. PlanSpatial.Data_exp = Data_aprob + 10 ani.
        3. Toate entitatile din ZFPropusa si ZonaReglementareSuplimentara
           primesc Data_aprob/Data_exp = cele din PlanSpatial.
        4. Prima entitate din ZFExistenta:
           a. daca Data_exp > PlanSpatial.Data_aprob, devine egala cu ea;
           b. daca (dupa a) Data_aprob nu e strict inaintea lui Data_exp,
              Data_aprob devine Data_exp - 10 ani;
           c. daca ambele criterii erau deja indeplinite, nu se schimba nimic.
        5. Toate celelalte entitati din ZFExistenta primesc Data_aprob/
           Data_exp = cele (eventual corectate) ale primei entitati.
    """
    result = FixResult()
    today = date.today()

    try:
        ps_layer = get_layer(project, "PlanSpatial")
        propusa_layer = get_layer(project, "ZFPropusa")
        zrs_layer = get_layer(project, "ZonaReglementareSuplimentara")
        existenta_layer = get_layer(project, "ZFExistenta")
    except ValueError as exc:
        result.note(str(exc))
        return result

    if ps_layer.featureCount() != 1:
        result.note(
            f"'PlanSpatial' trebuie sa contina exact o singura entitate "
            f"(are {ps_layer.featureCount()})."
        )
        return result

    ps_aprob_idx = ps_layer.fields().indexOf("Data_aprob")
    ps_exp_idx = ps_layer.fields().indexOf("Data_exp")
    if ps_aprob_idx < 0 or ps_exp_idx < 0:
        result.note("'PlanSpatial' nu are coloanele 'Data_aprob'/'Data_exp'.")
        return result

    ps_feat = next(ps_layer.getFeatures())
    ps_aprob = parse_date(ps_feat["Data_aprob"])
    if ps_aprob is None or ps_aprob > today:
        ps_aprob = today - timedelta(days=1)
    ps_exp = _year_shift(ps_aprob, 10)

    if not ps_layer.startEditing():
        result.note("'PlanSpatial': nu s-a putut porni editarea.")
        return result
    with _suppress_default_values(ps_layer):
        ps_layer.changeAttributeValue(ps_feat.id(), ps_aprob_idx, ps_aprob.isoformat())
        ps_layer.changeAttributeValue(ps_feat.id(), ps_exp_idx, ps_exp.isoformat())
        if ps_layer.commitChanges():
            result.changed += 1
        else:
            result.note(f"'PlanSpatial': commitChanges() a esuat - {ps_layer.commitErrors()}")
            ps_layer.rollBack()
            return result

    # ZFPropusa + ZonaReglementareSuplimentara: toate entitatile = datele PlanSpatial.
    for layer in (propusa_layer, zrs_layer):
        aidx = layer.fields().indexOf("Data_aprob")
        eidx = layer.fields().indexOf("Data_exp")
        if aidx < 0 or eidx < 0:
            result.note(f"'{layer.name()}' nu are coloanele 'Data_aprob'/'Data_exp'.")
            continue
        if not layer.startEditing():
            result.note(f"'{layer.name()}': nu s-a putut porni editarea.")
            continue
        count = 0
        with _suppress_default_values(layer):
            # feature-urile trebuie materializate INAINTE de a incepe sa
            # modificam campuri prin acelasi iterator - modificarea unui
            # strat in timp ce un QgsFeatureIterator asupra lui e inca
            # deschis poate face iteratia sa sara peste feature-uri
            # (confirmat empiric: fara list(...), doar o parte din straturi
            # ajungeau actualizate).
            for feat in list(layer.getFeatures()):
                layer.changeAttributeValue(feat.id(), aidx, ps_aprob.isoformat())
                layer.changeAttributeValue(feat.id(), eidx, ps_exp.isoformat())
                count += 1
            if layer.commitChanges():
                result.changed += count
            else:
                result.note(f"'{layer.name()}': commitChanges() a esuat - {layer.commitErrors()}")
                layer.rollBack()

    # ZFExistenta: prima entitate, apoi propagare la restul stratului.
    aidx = existenta_layer.fields().indexOf("Data_aprob")
    eidx = existenta_layer.fields().indexOf("Data_exp")
    if aidx < 0 or eidx < 0:
        result.note("'ZFExistenta' nu are coloanele 'Data_aprob'/'Data_exp'.")
        return result

    features = list(existenta_layer.getFeatures())
    if not features:
        result.note("'ZFExistenta' nu contine nicio entitate.")
        return result

    first = features[0]
    first_aprob = parse_date(first["Data_aprob"])
    first_exp = parse_date(first["Data_exp"])
    if first_aprob is None or first_exp is None:
        result.note(
            "'ZFExistenta' (prima entitate): 'Data_aprob'/'Data_exp' lipsesc - "
            "nu pot fi calculate automat."
        )
        return result

    changed_first = False
    if first_exp > ps_aprob:
        first_exp = ps_aprob
        changed_first = True
    if first_aprob >= first_exp:
        first_aprob = _year_shift(first_exp, -10)
        changed_first = True

    if not existenta_layer.startEditing():
        result.note("'ZFExistenta': nu s-a putut porni editarea.")
        return result

    count = 0
    with _suppress_default_values(existenta_layer):
        if changed_first:
            existenta_layer.changeAttributeValue(first.id(), aidx, first_aprob.isoformat())
            existenta_layer.changeAttributeValue(first.id(), eidx, first_exp.isoformat())
            count += 1
        for feat in features[1:]:
            cur_aprob = parse_date(feat["Data_aprob"])
            cur_exp = parse_date(feat["Data_exp"])
            if cur_aprob == first_aprob and cur_exp == first_exp:
                continue
            existenta_layer.changeAttributeValue(feat.id(), aidx, first_aprob.isoformat())
            existenta_layer.changeAttributeValue(feat.id(), eidx, first_exp.isoformat())
            count += 1

        if existenta_layer.commitChanges():
            result.changed += count
        else:
            result.note(f"'ZFExistenta': commitChanges() a esuat - {existenta_layer.commitErrors()}")
            existenta_layer.rollBack()

    return result


# -- registru: rule_id -> (eticheta buton, functie de fix) --------------------
#
# Regulile R18/R20/R21 sunt grupate sub aceeasi cheie (un singur buton) - vezi
# fix_temporal_redate. Cheia e un tuplu de rule_id-uri; UI-ul (results_dialog.py)
# afiseaza butonul daca ORICARE dintre ele are esecuri in rezultatele curente.

FIX_GROUPS = (
    {
        "rule_ids": (31,),
        "label": "Repara R31 (geometrie 2D)",
        "run": lambda project, rules: fix_geometry_2d(project, rules[31]),
    },
    {
        "rule_ids": (32,),
        "label": "Repara R32 (arie)",
        "run": lambda project, rules: fix_area_column(project, rules[32]),
    },
    {
        "rule_ids": (33,),
        "label": "Repara R33 (lungime)",
        "run": lambda project, rules: fix_length_column(project, rules[33]),
    },
    {
        "rule_ids": (34,),
        "label": "Repara R34 (suma arie intravilan)",
        "run": lambda project, rules: fix_intravilan_area_sum(project, rules[34]),
    },
    {
        "rule_ids": (26,),
        "label": "Repara R26 (clip la limita UAT)",
        "run": lambda project, rules: fix_clip_planspatial_to_uat(project, rules[26]),
    },
    {
        "rule_ids": (27,),
        "label": "Repara R27 (clip la limita PlanSpatial)",
        "run": lambda project, rules: fix_clip_to_planspatial(project, rules[27]),
    },
    {
        "rule_ids": TEMPORAL_REDATE_RULE_IDS,
        "label": "Repara R18/R20/R21 (recorelare temporala)",
        "run": lambda project, rules: fix_temporal_redate(project),
    },
)
