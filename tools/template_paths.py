# -*- coding: utf-8 -*-
"""
Rezolvarea caii catre sablonul PUG, folosita atat de "Proiect nou PUG"
(project_loader.py) cat si de "Editeaza sablonul" (template_editor.py).

Portabilitate intre calculatoare SI persistenta intre actualizari de plugin:

    Exista doua copii posibile ale sablonului:

    1. Sablonul "din fabrica" (bundled_template_dir): folderul templates/
       din interiorul plugin-ului. Este cel care calatoreste in arhiva .zip
       a plugin-ului si asigura portabilitatea pe un calculator nou. ATENTIE:
       de fiecare data cand plugin-ul este reinstalat/actualizat dintr-un
       .zip nou, acest folder este suprascris cu ce este inclus in acel .zip.

    2. Copia "activa" (active_template_dir): un folder in profilul QGIS
       (in afara folderului de instalare al plugin-ului), populat automat
       din sablonul din fabrica la prima utilizare. Aceasta copie este cea
       folosita efectiv pentru a crea proiecte noi si cea editata de
       "Editeaza sablonul" / "Salveaza sablonul". Pentru ca traieste in
       afara folderului plugin-ului, NU este atinsa de reinstalarea sau
       actualizarea plugin-ului - modificarile facute prin plugin (structura,
       stiluri, proprietati de camp) persista intre versiuni.

    O a treia optiune, suprascrierea manuala din QGIS Settings
    (SETTINGS_TEMPLATE_DIR_KEY), are prioritate fata de ambele - utila daca
    o echipa prefera un sablon central pe o unitate de retea in loc de
    copia locala din profil.
"""

import os
import shutil
import sqlite3

from qgis.core import QgsApplication, QgsSettings

TEMPLATE_NAME = "JUD_UAT_SIRUTA_PUG_AAAALLZZ"
GPKG_FOLDER = "0_Seturi_date_spatiale/"
GPKG_RELATIVE = GPKG_FOLDER + TEMPLATE_NAME + ".gpkg"

SETTINGS_TEMPLATE_DIR_KEY = "PUGTools/template_dir"


class TemplateNotFoundError(Exception):
    """Ridicata cand niciun sablon (suprascris, activ sau din fabrica) nu poate fi gasit."""


def _normalize(path):
    return path.replace("\\", "/").rstrip("/") + "/"


def plugin_dir():
    """Folderul radacina al plugin-ului (un nivel deasupra tools/)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def bundled_template_dir():
    """Sablonul "din fabrica", livrat cu plugin-ul - suprascris la fiecare update de plugin."""
    return _normalize(os.path.join(plugin_dir(), "templates", TEMPLATE_NAME))


def active_template_root():
    """Folder in profilul QGIS unde traieste copia de lucru a sablonului."""
    base = QgsApplication.qgisSettingsDirPath()
    return os.path.join(base, "PUGTools", "templates")


def active_template_dir():
    return _normalize(os.path.join(active_template_root(), TEMPLATE_NAME))


def resolve_template_dir(ensure_active_copy=True):
    """
    Determina folderul sablon de folosit, in ordine:
        1. Suprascriere manuala din QGIS Settings (SETTINGS_TEMPLATE_DIR_KEY).
        2. Copia activa din profilul QGIS; daca nu exista inca si
           ensure_active_copy=True, este creata automat dintr-o copie a
           sablonului din fabrica (daca acesta exista).
        3. Sablonul din fabrica, direct, daca copia activa tot nu exista.

    Ridica TemplateNotFoundError cu un mesaj clar daca niciuna dintre cele
    de mai sus nu poate fi folosita.
    """
    settings = QgsSettings()
    override = settings.value(SETTINGS_TEMPLATE_DIR_KEY, "", type=str)
    if override:
        path = _normalize(override)
        if not os.path.isdir(path):
            raise TemplateNotFoundError(
                "Calea suprascrisa manual in QGIS Settings "
                f"('{SETTINGS_TEMPLATE_DIR_KEY}') nu exista:\n{path}"
            )
        return path

    active = active_template_dir()
    if ensure_active_copy and not os.path.isdir(active):
        bundled = bundled_template_dir()
        if os.path.isdir(bundled):
            os.makedirs(active_template_root(), exist_ok=True)
            shutil.copytree(bundled, active.rstrip("/"))

    if os.path.isdir(active):
        return active

    bundled = bundled_template_dir()
    if os.path.isdir(bundled):
        return bundled

    raise TemplateNotFoundError(
        "Nu s-a gasit niciun sablon (nici copie activa in profilul QGIS, nici "
        "sablon inclus in plugin).\n\n"
        f"Cale asteptata (copie activa): {active}\n"
        f"Cale asteptata (inclusa in plugin): {bundled}\n\n"
        "Vezi README.md din folderul 'templates/' al plugin-ului."
    )


# -- gestiune (folosita de dialogul "Despre") ---------------------------------
# Functii separate de resolve_template_dir(), pentru a putea afisa starea
# fiecarei surse de sablon (cu cale completa) si a oferi actiuni de
# stergere/reimprospatare a copiei active din UI.

def override_template_dir():
    """Calea suprascrisa manual in QGIS Settings, sau None daca nu e setata."""
    settings = QgsSettings()
    override = settings.value(SETTINGS_TEMPLATE_DIR_KEY, "", type=str)
    return _normalize(override) if override else None


def active_copy_gpkg_path():
    return active_template_dir() + GPKG_RELATIVE


def active_copy_exists():
    return os.path.isfile(active_copy_gpkg_path())


def bundled_gpkg_path():
    return bundled_template_dir() + GPKG_RELATIVE


def bundled_exists():
    return os.path.isfile(bundled_gpkg_path())


def _gpkg_versiune(gpkg_path):
    """Numarul de versiune (str) din tabela "sys__versiune" (sabloane >= 3.1.0)
    sau "__versiune" (sabloane mai vechi) a unui gpkg, sau None daca
    fisierul/tabela nu exista ori nu poate fi citita."""
    if not os.path.isfile(gpkg_path):
        return None
    try:
        con = sqlite3.connect(gpkg_path)
        try:
            cur = con.cursor()
            for table in ("sys__versiune", "__versiune"):
                try:
                    cur.execute(f'SELECT versiune FROM "{table}" LIMIT 1')
                except sqlite3.OperationalError:
                    continue  # tabela nu exista in acest sablon
                row = cur.fetchone()
                return row[0] if row else None
            return None
        finally:
            con.close()
    except sqlite3.DatabaseError:
        return None


def active_copy_outdated():
    """
    True daca exista o copie activa a sablonului SI numarul de versiune din
    tabela "sys__versiune" a sablonului din fabrica (bundled cu plugin-ul)
    difera de cel al copiei active - caz tipic dupa o actualizare de plugin
    care aduce o schema noua de sablon (ex. schimbarea structurii "_siruta"
    in 3.0.3), dar copia activa (cea folosita efectiv de "Proiect nou PUG"
    si "Actualizeaza pachetul" - vezi resolve_template_dir) ramane pe schema
    veche pana este reimprospatata manual din dialogul "Despre" - nu e
    reimprospatata automat ca sa nu se piarda fara avertisment eventuale
    personalizari facute de utilizator prin "Editeaza sablonul"/"Salveaza
    sablonul".
    """
    if not active_copy_exists():
        return False
    bundled_versiune = _gpkg_versiune(bundled_gpkg_path())
    active_versiune = _gpkg_versiune(active_copy_gpkg_path())
    if bundled_versiune is None or active_versiune is None:
        return False
    return bundled_versiune != active_versiune


def delete_active_copy():
    """
    Sterge folderul copiei active a sablonului, daca exista. Urmatoarea
    creare de proiect il recreeaza automat din sablonul din fabrica (vezi
    resolve_template_dir). ATENTIE: elimina orice modificare facuta prin
    "Editeaza sablonul"/"Salveaza sablonul" si nesalvata inca in sablonul
    din fabrica.
    """
    path = active_template_dir().rstrip("/")
    if os.path.isdir(path):
        shutil.rmtree(path)
        return True
    return False


def refresh_active_copy():
    """
    Sterge (daca exista) si recreeaza imediat copia activa din sablonul din
    fabrica - util pentru a prelua manual actualizari aduse sablonului
    bundled cu plugin-ul, fara a astepta prima creare de proiect. Aceeasi
    atentionare ca la delete_active_copy() cu privire la modificari nesalvate.
    """
    bundled = bundled_template_dir()
    if not os.path.isdir(bundled):
        raise TemplateNotFoundError(
            f"Sablonul din fabrica (inclus in plugin) nu a fost gasit:\n{bundled}"
        )
    delete_active_copy()
    os.makedirs(active_template_root(), exist_ok=True)
    shutil.copytree(bundled, active_template_dir().rstrip("/"))
