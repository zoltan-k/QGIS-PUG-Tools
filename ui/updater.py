# -*- coding: utf-8 -*-
"""
Verificare si instalare actualizari, doar la cererea utilizatorului (butonul
din dialogul "Despre"). Interogheaza ULTIMA versiune publica (GitHub Releases
al repo-ului public), descarca zip-ul atasat si il instaleaza prin
installerul QGIS (acelasi cod ca "Instaleaza din ZIP" din Plugin Manager).

Fisier identic in repo-ul intern si in cel public: URL-ul tinteste mereu
release-ul public.
"""

import hashlib
import json
import os
import re
import shutil
import tempfile
import zipfile

from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest

from qgis.core import QgsBlockingNetworkRequest

PUBLIC_REPO = "zoltan-k/QGIS-PUG-Tools"
LATEST_API_URL = f"https://api.github.com/repos/{PUBLIC_REPO}/releases/latest"
PLUGIN_FOLDER = "PUGTools"
_TIMEOUT_MS = 20000
_DOWNLOAD_TIMEOUT_MS = 120000


class UpdateError(Exception):
    pass


def parse_version(text):
    """'v2.2.5.0' -> (2, 2, 5, 0); eroare daca nu e numeric."""
    parts = str(text).strip().lstrip("vV").split(".")
    try:
        return tuple(int(p) for p in parts)
    except ValueError:
        raise UpdateError(f"Versiune necunoscuta: {text!r}")


def is_newer(remote, local):
    a, b = parse_version(remote), parse_version(local)
    width = max(len(a), len(b))
    pad = lambda t: t + (0,) * (width - len(t))
    return pad(a) > pad(b)


def _get(url, timeout_ms):
    request = QNetworkRequest(QUrl(url))
    request.setRawHeader(b"Accept", b"application/vnd.github+json")
    request.setTransferTimeout(timeout_ms)
    blocking = QgsBlockingNetworkRequest()
    err = blocking.get(request, forceRefresh=True)
    if err != QgsBlockingNetworkRequest.NoError:
        raise UpdateError(blocking.errorMessage() or "Eroare de retea")
    return bytes(blocking.reply().content())


def fetch_latest_release():
    """Returneaza dict cu: version, notes, page_url, asset_name, asset_url,
    asset_size, sha256 (poate fi None)."""
    try:
        data = json.loads(_get(LATEST_API_URL, _TIMEOUT_MS).decode("utf-8"))
    except UpdateError:
        raise
    except ValueError:
        raise UpdateError("Raspuns invalid de la GitHub.")

    tag = data.get("tag_name")
    if not tag:
        raise UpdateError("Nu exista nicio versiune publicata.")
    version = ".".join(str(n) for n in parse_version(tag))

    assets = [a for a in data.get("assets", []) if a.get("name", "").lower().endswith(".zip")]
    asset = None
    for candidate in assets:
        if re.match(r"^PUGTools.*\.zip$", candidate["name"]):
            asset = candidate
            break
    if asset is None and assets:
        asset = assets[0]

    digest = (asset or {}).get("digest") or ""
    sha256 = digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else None

    return {
        "version": version,
        "notes": (data.get("body") or "").strip(),
        "page_url": data.get("html_url") or f"https://github.com/{PUBLIC_REPO}/releases/latest",
        "asset_name": (asset or {}).get("name"),
        "asset_url": (asset or {}).get("browser_download_url"),
        "asset_size": (asset or {}).get("size"),
        "sha256": sha256,
    }


def install_block_reason(plugin_dir):
    """Motiv pentru care instalarea automata nu e sigura (sau None).

    Installerul QGIS sterge folderul plugin-ului si dezarhiveaza peste el;
    pe o copie de dezvoltare (legatura/junction sau checkout git) ar sterge
    sursele reale.
    """
    if os.path.islink(plugin_dir) or os.path.realpath(plugin_dir) != os.path.abspath(plugin_dir):
        return "plugin-ul ruleaza dintr-o legatura (copie de dezvoltare)"
    if os.path.exists(os.path.join(plugin_dir, ".git")):
        return "folderul plugin-ului este un checkout git (copie de dezvoltare)"
    if os.path.basename(os.path.normpath(plugin_dir)) != PLUGIN_FOLDER:
        return f"folderul plugin-ului nu se numeste {PLUGIN_FOLDER}"
    return None


def download_release(release, dest_dir):
    """Descarca zip-ul si il valideaza. Returneaza calea fisierului."""
    if not release.get("asset_url"):
        raise UpdateError("Versiunea publicata nu contine un fisier zip.")
    if not release["asset_url"].lower().startswith("https://"):
        raise UpdateError("Adresa de descarcare nu este HTTPS.")

    content = _get(release["asset_url"], _DOWNLOAD_TIMEOUT_MS)

    if release.get("sha256"):
        actual = hashlib.sha256(content).hexdigest()
        if actual != release["sha256"]:
            raise UpdateError("Suma de control (SHA-256) a fisierului descarcat nu corespunde.")

    path = os.path.join(dest_dir, os.path.basename(release["asset_name"]))
    with open(path, "wb") as handle:
        handle.write(content)

    try:
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                raise UpdateError("Arhiva zip descarcata este deteriorata.")
            meta_name = f"{PLUGIN_FOLDER}/metadata.txt"
            if meta_name not in archive.namelist():
                raise UpdateError(f"Arhiva nu contine {meta_name}.")
            meta_text = archive.read(meta_name).decode("utf-8", "replace")
    except zipfile.BadZipFile:
        raise UpdateError("Fisierul descarcat nu este o arhiva zip valida.")

    match = re.search(r"^version\s*=\s*(\S+)", meta_text, re.MULTILINE)
    if not match or parse_version(match.group(1)) != parse_version(release["version"]):
        raise UpdateError("Versiunea din arhiva nu corespunde versiunii anuntate.")
    return path


def backup_current(plugin_dir, current_version):
    """Copie a versiunii curente in folderul temporar (in afara folderului de
    plugin-uri, ca sa nu fie incarcata ca plugin). Returneaza calea."""
    backup = os.path.join(tempfile.gettempdir(), f"PUGTools_backup_{current_version}")
    if os.path.exists(backup):
        shutil.rmtree(backup, ignore_errors=True)
    shutil.copytree(plugin_dir, backup, ignore=shutil.ignore_patterns("__pycache__"))
    return backup


def install_zip(zip_path):
    """Instaleaza prin installerul QGIS (descarca/inlocuieste si reincarca)."""
    import pyplugin_installer

    pyplugin_installer.instance().installFromZipFile(zip_path)
