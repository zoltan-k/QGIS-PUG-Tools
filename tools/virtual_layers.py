# -*- coding: utf-8 -*-
"""
Straturi de referinta "virtuale" (provider QGIS "virtual" - o interogare SQL
peste alte straturi deja incarcate, fara tabel propriu in fisierul GPKG).

Definitie comuna, folosita atat de project_loader.py (la crearea unui
proiect nou) cat si de package_updater.py (verifica/reconstruieste la
actualizare), ca cele doua unelte sa nu poata ajunge sa foloseasca
interogari diferite intre ele.

Interogarea trebuie transmisa catre provider-ul "virtual" deja procentual-
codificata ca UTF-8, nu ca text brut. Confirmat empiric: QGIS re-codifica
sursa unui strat "virtual" la salvarea proiectului (.qgz), dar codificarea
folosita pentru caracterele care nu incap direct intr-un URI NU e UTF-8 -
diacriticele romanesti ("ă", "â", "î", "ș", "ț") din interogare, lasate ca
text brut, devin literalmente "?" in fisierul salvat pe disc (verificat
direct in XML-ul din interiorul .qgz, nu doar la re-deschidere - coruptia
se intampla la SALVARE, nu la citire). Aceleasi caractere, procentual-
codificate INAINTE sa ajunga la acel pas (ex. "ă" -> "%C4%83"), trec
neatinse. Fara aceasta masura, ORICE proiect nou creat ar salva o
interogare corupta chiar de la prima salvare - nu doar proiectele vechi.
"""

from urllib.parse import quote, unquote

from qgis.core import QgsVectorLayer

VREF_SZF_ZRS_D_NAME = "~vREF_SZF_ZRS_D"

VREF_SZF_ZRS_D_QUERY = """SELECT
    "SZF" as shortc,
    Cod_SZF as Cod,
    Tip_SZF as Tip,
    "Subzonă funcțională" as Tip_zona
FROM "~REF_SZF"
UNION
SELECT
    "ZRS_D" as shortc,
    Cod_ZRS_D as Cod,
    Tip_ZRS_D as Tip,
    "Zonă de reglementare suplimentară de detaliu" as Tip_zona
FROM "~REF_ZRS_D"
"""

# nume strat -> interogarea lui canonica. Adauga aici orice alt strat
# virtual de referinta viitor, ca sa fie acoperit automat si de
# package_updater.py._sync_virtual_ref_layers().
VREF_QUERIES = {VREF_SZF_ZRS_D_NAME: VREF_SZF_ZRS_D_QUERY}


def create_vref_layer(name):
    """Construieste (fara sa il adauge in proiect) un strat virtual de referinta cunoscut, dupa nume."""
    query = VREF_QUERIES[name]
    encoded_query = quote(query, safe="")
    return QgsVectorLayer(f"?query={encoded_query}&nogeometry", name, "virtual")


def current_query(layer):
    """
    Interogarea SQL curenta a unui strat "virtual" deja incarcat (decodificata,
    text brut), sau None daca stratul nu pare a fi unul construit de
    create_vref_layer() (sursa nu contine un parametru "query=").
    """
    source = layer.source()
    marker = "query="
    start = source.find(marker)
    if start < 0:
        return None
    start += len(marker)
    end = source.find("&", start)
    encoded = source[start:] if end < 0 else source[start:end]
    return unquote(encoded)
