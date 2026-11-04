# -*- coding: utf-8 -*-
"""
Verificare automata inainte de "cpr" (commit + push + release) - NU face parte
din plugin si NU se pune in arhiva .zip (folderul dev/ e exclus).

Ruleaza cu Python-ul de sistem (doar biblioteca standard):

    py -3.15 dev/cpr_precheck.py            # avertismente, exit 0
    py -3.15 dev/cpr_precheck.py --strict   # exit 1 daca exista avertismente
    py -3.15 dev/cpr_precheck.py --skip-nvd # sare peste interogarile NVD (lente)

Ce verifica (tot ce nu e in regula devine o linie "WARNING:"):
  1. SBOM.cdx.json e coerent cu realitatea: versiunea din metadata.txt, hash-ul
     sablonului, versiunile QGIS/PyQt/GDAL/Python/SQLite din instalarile de test
     si versiunile uneltelor (7-Zip, Git, gh, osv-scanner, Python de sistem).
  2. Actualizari disponibile: QGIS (3.x si 4.x), unelte prin winget, plus -
     informativ - versiuni noi upstream pentru bibliotecile livrate cu QGIS.
  3. Vulnerabilitati: osv-scanner pe SBOM (componente cu purl pypi/golang) si
     NVD (CPE) pentru componentele "generic" pe care OSV nu le poate potrivi.
     Potrivirea NVD pe CPE e grosiera - tratati rezultatele ca "de revizuit".
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SBOM_PATH = os.path.join(ROOT, "SBOM.cdx.json")
TEMPLATE_GPKG = os.path.join(
    ROOT, "templates", "JUD_UAT_SIRUTA_PUG_AAAALLZZ", "0_Seturi_date_spatiale",
    "JUD_UAT_SIRUTA_PUG_AAAALLZZ.gpkg",
)
OSV_CANDIDATES = [
    shutil.which("osv-scanner"),
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\osv-scanner.exe"),
]
HTTP_TIMEOUT = 25

warnings = []
found_cves = []  # (bom-ref, id, severity text, score, description)


def warn(msg):
    warnings.append(msg)
    print("WARNING: " + msg)


def info(msg):
    print("  " + msg)


def section(title):
    print("\n== " + title)


def http_get(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": "pugtools-precheck", **(headers or {})})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return resp.read().decode("utf-8", "replace")


def http_json(url, headers=None):
    return json.loads(http_get(url, headers))


def run(cmd, timeout=180):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, errors="replace")
        return out.returncode, (out.stdout or "") + (out.stderr or "")
    except (OSError, subprocess.SubprocessError) as exc:
        return -1, str(exc)


def vtuple(text):
    return tuple(int(p) for p in re.findall(r"\d+", text)[:4])


# -- 1. SBOM <-> realitate ---------------------------------------------------

QGIS_PROBE = (
    "import sys, sqlite3, json\n"
    "from qgis.core import Qgis\n"
    "from qgis.PyQt.QtCore import QT_VERSION_STR, PYQT_VERSION_STR\n"
    "from osgeo import gdal\n"
    "print('PROBE' + json.dumps({'qgis': Qgis.version().split('-')[0], 'qt': QT_VERSION_STR,"
    " 'pyqt': PYQT_VERSION_STR, 'gdal': gdal.__version__, 'python': sys.version.split()[0],"
    " 'sqlite': sqlite3.sqlite_version}))\n"
)


def probe_qgis(install_dir):
    bin_dir = os.path.join(install_dir, "bin")
    bat = next(
        (os.path.join(bin_dir, n) for n in ("python-qgis-ltr.bat", "python-qgis.bat")
         if os.path.isfile(os.path.join(bin_dir, n))),
        None,
    )
    if bat is None:
        return None
    tmp = tempfile.mkdtemp(prefix="pugprobe_")
    try:
        script = os.path.join(tmp, "probe.py")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write(QGIS_PROBE)
        code, out = run([bat, script], timeout=240)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for line in out.splitlines():
        if line.startswith("PROBE"):
            return json.loads(line[5:])
    return None


def tool_version(cmd, regex):
    code, out = run(cmd, timeout=30)
    m = re.search(regex, out)
    return m.group(1) if m else None


def check_sbom(sbom):
    section("1. SBOM vs installed reality")
    comps = {c["bom-ref"]: c for c in sbom.get("components", []) if "bom-ref" in c}

    meta = open(os.path.join(ROOT, "metadata.txt"), encoding="utf-8").read()
    plugin_version = re.search(r"^version=(\S+)", meta, re.M).group(1)
    sbom_version = sbom["metadata"]["component"]["version"]
    if plugin_version != sbom_version:
        warn(f"SBOM plugin version {sbom_version} != metadata.txt {plugin_version}")

    with open(TEMPLATE_GPKG, "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    declared = comps["asset-template-gpkg"]["hashes"][0]["content"]
    if digest != declared:
        warn(f"template gpkg SHA-256 changed (SBOM has {declared[:12]}..., file is {digest[:12]}...) - update SBOM")

    installs = {}
    for ref in ("runtime-qgis", "runtime-qgis-qt6"):
        comp = comps[ref]
        path = next((p["value"] for p in comp.get("properties", []) if p["name"] == "sbom:install-path"), None)
        if path is None:  # default Windows install location for this QGIS version
            path = f"C:/Program Files/QGIS {comp['version']}"
        probe = probe_qgis(path) if path and os.path.isdir(path) else None
        if probe is None:
            warn(f"{comp['name']}: install {path!r} not found / probe failed")
            continue
        installs[ref] = probe
        info(f"{comp['name']}: {probe}")
        if probe["qgis"] != comp["version"]:
            warn(f"{comp['name']}: installed {probe['qgis']} but SBOM says {comp['version']}")
        pyqt_ref = "runtime-pyqt5" if probe["qt"].startswith("5") else "runtime-pyqt6"
        for ref2, key in ((pyqt_ref, "pyqt"), ("runtime-gdal", "gdal"), ("runtime-python", "python"), ("runtime-sqlite", "sqlite")):
            if probe[key] != comps[ref2]["version"]:
                warn(f"{comps[ref2]['name']}: {comp['name']} has {probe[key]} but SBOM says {comps[ref2]['version']}")

    tools = {
        "tool-7zip": (["7z"], r"7-Zip[^\d]*([\d.]+)"),
        "tool-git": (["git", "--version"], r"git version ([\w.]+)"),
        "tool-gh": (["gh", "--version"], r"gh version ([\d.]+)"),
        "tool-osv-scanner": ([OSV_CANDIDATES[0] or OSV_CANDIDATES[1], "--version"], r"([\d]+\.[\d]+\.[\d]+)"),
        "tool-system-python": ([sys.executable, "--version"], r"Python ([\d.]+)"),
    }
    seven = r"C:\Program Files\7-Zip\7z.exe"
    if not shutil.which("7z") and os.path.isfile(seven):
        tools["tool-7zip"] = ([seven], tools["tool-7zip"][1])
    for ref, (cmd, rx) in tools.items():
        comp = comps[ref]
        found = tool_version(cmd, rx)
        if found is None:
            warn(f"{comp['name']}: not found / version unreadable (SBOM says {comp['version']})")
        elif found.replace("windows.", "").rstrip(".") not in comp["version"].replace("windows.", ""):
            warn(f"{comp['name']}: installed {found} but SBOM says {comp['version']}")
        else:
            info(f"{comp['name']}: {found} ok")
    return comps


# -- 2. actualizari -----------------------------------------------------------

def latest_qgis_3(minor):
    """Cel mai nou patch final-3_<minor>_N si cel mai nou minor 3.x (din tag-uri GitHub)."""
    tags = []
    for page in (1, 2, 3):
        try:
            data = http_json(f"https://api.github.com/repos/qgis/QGIS/tags?per_page=100&page={page}")
        except (urllib.error.URLError, OSError, ValueError):
            break
        tags += [t["name"] for t in data]
    versions = [tuple(map(int, m.groups())) for t in tags if (m := re.fullmatch(r"final-(3)_(\d+)_(\d+)", t))]
    same_minor = [v for v in versions if v[1] == minor]
    return (max(same_minor) if same_minor else None), (max(versions) if versions else None)


def check_updates(sbom, comps):
    section("2. Available updates")
    try:
        text = http_get("https://version.qgis.org/version.txt")
        m = re.search(r"QGIS Version (\d+)", text)
        latest4 = (int(m.group(1)) // 10000, (int(m.group(1)) // 100) % 100, int(m.group(1)) % 100)
        cur = vtuple(comps["runtime-qgis-qt6"]["version"])
        info(f"QGIS latest release: {'.'.join(map(str, latest4))} (installed 4.x: {comps['runtime-qgis-qt6']['version']})")
        if latest4 > cur:
            warn(f"QGIS {'.'.join(map(str, latest4))} available (4.x installed: {comps['runtime-qgis-qt6']['version']})")
    except (urllib.error.URLError, OSError, AttributeError):
        warn("could not query version.qgis.org")

    cur3 = vtuple(comps["runtime-qgis"]["version"])
    patch, newest = latest_qgis_3(cur3[1])
    if patch is None:
        warn("could not query GitHub tags for QGIS 3.x")
    else:
        info(f"QGIS 3.{cur3[1]} latest patch: {'.'.join(map(str, patch))}; newest 3.x: {'.'.join(map(str, newest))}")
        if patch > cur3:
            warn(f"QGIS {'.'.join(map(str, patch))} available for the 3.{cur3[1]} line (installed {comps['runtime-qgis']['version']})")
        elif newest and newest[:2] > cur3[:2]:
            info(f"note: a newer 3.x minor exists ({'.'.join(map(str, newest))}) - check whether it is the new LTR")

    # unelte prin winget
    code, out = run(["winget", "upgrade", "--accept-source-agreements"], timeout=120)
    if code == -1 or "Id" not in out:
        warn("winget upgrade could not be queried")
    else:
        for ref in ("tool-7zip", "tool-git", "tool-gh", "tool-osv-scanner", "tool-system-python"):
            comp = comps[ref]
            wid = next((p["value"] for p in comp.get("properties", []) if p["name"] == "winget:id"), None)
            for line in out.splitlines():
                cols = re.split(r"\s{2,}", line.strip())
                if len(cols) >= 4 and cols[1] == wid:
                    warn(f"{comp['name']}: winget has {cols[3]} (installed {cols[2]}) - run: winget upgrade --id {wid}")
                    break
            else:
                info(f"{comp['name']}: up to date per winget")

    # biblioteci livrate cu QGIS - informativ (se actualizeaza odata cu QGIS)
    def pypi_latest(name):
        try:
            return http_json(f"https://pypi.org/pypi/{name}/json")["info"]["version"]
        except (urllib.error.URLError, OSError, ValueError, KeyError):
            return None

    for ref, pypi in (("runtime-pyqt5", "PyQt5"), ("runtime-pyqt6", "PyQt6"), ("runtime-gdal", "GDAL")):
        latest = pypi_latest(pypi)
        have = comps[ref]["version"]
        if latest and vtuple(latest) > vtuple(have):
            info(f"bundled {comps[ref]['name']}: {latest} on PyPI (QGIS ships {have}) - arrives with a QGIS update")
    for ref, product, cycle_prefix in (("runtime-sqlite", "sqlite", None), ("runtime-python", "python", None)):
        try:
            data = http_json(f"https://endoflife.date/api/{product}.json")
            have = comps[ref]["version"]
            cycle = next((c for c in data if have.startswith(c["cycle"] + ".") or have == c["cycle"]), None)
            if cycle is None and product == "sqlite":
                cycle = data[0]
            if cycle and vtuple(cycle["latest"]) > vtuple(have):
                info(f"bundled {comps[ref]['name']}: {cycle['latest']} upstream (QGIS ships {have}) - arrives with a QGIS update")
            if product == "python" and cycle and cycle.get("eol") and str(cycle["eol"]) < time.strftime("%Y-%m-%d"):
                warn(f"Python {cycle['cycle']} embedded in QGIS is end-of-life since {cycle['eol']}")
        except (urllib.error.URLError, OSError, ValueError, KeyError):
            pass


# -- 3. vulnerabilitati -----------------------------------------------------

NVD_CPES = {
    "runtime-qgis": "cpe:2.3:a:qgis:qgis:{v}:*:*:*:*:*:*:*",
    "runtime-qgis-qt6": "cpe:2.3:a:qgis:qgis:{v}:*:*:*:*:*:*:*",
    "runtime-python": "cpe:2.3:a:python:python:{v}:*:*:*:*:*:*:*",
    "runtime-sqlite": "cpe:2.3:a:sqlite:sqlite:{v}:*:*:*:*:*:*:*",
    "runtime-gdal": "cpe:2.3:a:osgeo:gdal:{v}:*:*:*:*:*:*:*",
    "tool-7zip": "cpe:2.3:a:7-zip:7-zip:{v}:*:*:*:*:*:*:*",
    "tool-git": "cpe:2.3:a:git-scm:git:{v}:*:*:*:*:*:*:*",
}


def nvd_affects(cve, prefix, version):
    """
    True daca un CVE afecteaza REALMENT `version` a produsului (criteriu CPE cu
    `prefix`): doar potriviri "vulnerable" (nu "ruleaza pe"/platforma din
    configuratii AND), cu versiunea in intervalul declarat. CVE-uri fara
    configuratii (nca neanalizate) sunt pastrate - revizuire manuala.
    """
    nodes = [n for c in cve.get("configurations", []) for n in c.get("nodes", [])]
    if not nodes:
        return True
    have = vtuple(version)
    for node in nodes:
        for m in node.get("cpeMatch", []):
            if not m.get("vulnerable") or not m["criteria"].startswith(prefix):
                continue
            crit_ver = m["criteria"].split(":")[5]
            ranged = any(k in m for k in ("versionStartIncluding", "versionStartExcluding",
                                          "versionEndIncluding", "versionEndExcluding"))
            if not ranged:
                if crit_ver in ("*", "-") or vtuple(crit_ver) == have:
                    return True
                continue
            ok = True
            if "versionStartIncluding" in m and have < vtuple(m["versionStartIncluding"]):
                ok = False
            if "versionStartExcluding" in m and have <= vtuple(m["versionStartExcluding"]):
                ok = False
            if "versionEndIncluding" in m and have > vtuple(m["versionEndIncluding"]):
                ok = False
            if "versionEndExcluding" in m and have >= vtuple(m["versionEndExcluding"]):
                ok = False
            if ok:
                return True
    return False


def check_vulns(sbom, comps, skip_nvd):
    section("3. Vulnerabilities")
    recorded = {v["id"]: v.get("analysis", {}).get("state", "in_triage") for v in sbom.get("vulnerabilities", [])}
    osv = next((p for p in OSV_CANDIDATES if p and os.path.isfile(p)), None)
    if osv is None:
        warn("osv-scanner not found (winget install Google.OSVScanner) - OSV scan skipped")
    else:
        tmp_out = os.path.join(tempfile.mkdtemp(prefix="pugosv_"), "osv.json")
        code, out = run([osv, "scan", "source", "-L", SBOM_PATH, "--format", "json",
                         "--output-file", tmp_out], timeout=240)
        try:
            with open(tmp_out, encoding="utf-8") as fh:
                data = json.load(fh)
            vulns = [(p["package"]["name"], p["package"]["version"], v["id"])
                     for r in data.get("results", []) for p in r.get("packages", []) for v in p.get("vulnerabilities", [])]
        except ValueError:
            vulns = None
        if vulns is None:
            warn("osv-scanner output could not be parsed (exit %s)" % code)
        elif vulns:
            for name, ver, vid in sorted(set(vulns)):
                warn(f"OSV: {name} {ver}: {vid}")
        else:
            info("OSV (pypi/golang components): no known vulnerabilities")

    if skip_nvd:
        info("NVD check skipped (--skip-nvd)")
        return
    delay = 0.7 if os.environ.get("NVD_API_KEY") else 6.5
    headers = {"apiKey": os.environ["NVD_API_KEY"]} if os.environ.get("NVD_API_KEY") else {}
    seen = set()
    for ref, tmpl in NVD_CPES.items():
        comp = comps[ref]
        version = re.sub(r"\.windows\.\d+", "", comp["version"])
        cpe = tmpl.format(v=version)
        if cpe in seen:
            continue
        seen.add(cpe)
        url = "https://services.nvd.nist.gov/rest/json/cves/2.0?" + urllib.parse.urlencode(
            {"cpeName": cpe, "resultsPerPage": 40})
        try:
            data = http_json(url, headers)
        except urllib.error.HTTPError as exc:
            info(f"NVD {comp['name']} {version}: not checkable (HTTP {exc.code})")
            time.sleep(delay)
            continue
        except (urllib.error.URLError, OSError, ValueError):
            warn(f"NVD query failed for {comp['name']} {version}")
            continue
        items = data.get("vulnerabilities", [])
        total = data.get("totalResults", len(items))
        # NVD potriveste grosier (ex. CVE-uri PHP care mentioneaza sqlite) - se afiseaza
        # pentru revizuire manuala, fara "In PHP" si fara intrari respinse.
        shown = []
        prefix = tmpl.split("{v}")[0]
        for it in items:
            cve = it["cve"]
            if cve.get("vulnStatus") == "Rejected":
                continue
            if not nvd_affects(cve, prefix, version):
                continue
            desc = next((d["value"] for d in cve.get("descriptions", []) if d["lang"] == "en"), "")
            if desc.startswith(("In PHP", "PHP ")):
                continue
            sev = ""
            for key in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30"):
                if cve.get("metrics", {}).get(key):
                    m = cve["metrics"][key][0]["cvssData"]
                    sev = f"{m.get('baseSeverity', '')} {m.get('baseScore', '')}"
                    break
            shown.append((cve["id"], sev, desc))
        new = [t for t in shown if t[0] not in recorded]
        open_ = [t for t in shown if recorded.get(t[0]) in ("in_triage", "exploitable")]
        known = [t for t in shown if t[0] in recorded and t not in open_]
        for cid, sev, desc in shown:
            found_cves.append((ref, cid, sev, desc))
        if known:
            info(f"NVD {comp['name']} {version}: {len(known)} finding(s) triaged as not affected/resolved in the SBOM: "
                 + ", ".join(t[0] for t in known))
        if open_:
            warn(f"NVD: {comp['name']} {version}: {len(open_)} open finding(s) (in_triage/exploitable in the SBOM; "
                 "fixed only by upgrading the host/tool): " + ", ".join(t[0] for t in open_))
        if new:
            warn(f"NVD: {comp['name']} {version}: {len(new)} NEW CVE(s) not yet in the SBOM - review: "
                 + "; ".join(f"{i} [{sv}]" for i, sv, _ in new[:8]) + (" ..." if len(new) > 8 else "")
                 + "  (record with --write-vex after triage)")
        elif not shown:
            info(f"NVD {comp['name']} {version}: no matching CVEs (total {total} before filtering)")
        time.sleep(delay)


def write_vex(sbom):
    """Adauga in SBOM (sectiunea CycloneDX 'vulnerabilities') CVE-urile gasite si inca
    nerecordate, cu starea 'in_triage' - starea se rafineaza apoi manual
    (not_affected / exploitable / resolved)."""
    existing = {v["id"] for v in sbom.setdefault("vulnerabilities", [])}
    added = 0
    for ref, cid, sev, desc in found_cves:
        if cid in existing:
            continue
        sev_name, _, score = sev.partition(" ")
        rating = {"source": {"name": "NVD"}}
        if sev_name:
            rating["severity"] = sev_name.lower()
        if score:
            rating["score"] = float(score)
        sbom["vulnerabilities"].append({
            "id": cid,
            "source": {"name": "NVD", "url": f"https://nvd.nist.gov/vuln/detail/{cid}"},
            "ratings": [rating],
            "description": desc[:300],
            "analysis": {"state": "in_triage",
                         "detail": "Found by dev/cpr_precheck.py on " + time.strftime("%Y-%m-%d")
                                   + ". Component is supplied by the host (QGIS) or a dev tool; fixed only by upgrading it."},
            "affects": [{"ref": ref}],
        })
        existing.add(cid)
        added += 1
    with open(SBOM_PATH, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(sbom, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(f"SBOM updated: {added} vulnerability record(s) added (state in_triage).")


def main():
    strict = "--strict" in sys.argv
    with open(SBOM_PATH, encoding="utf-8") as fh:
        sbom = json.load(fh)
    comps = check_sbom(sbom)
    check_updates(sbom, comps)
    check_vulns(sbom, comps, "--skip-nvd" in sys.argv)
    if "--write-vex" in sys.argv:
        write_vex(sbom)
    section("Summary")
    if warnings:
        print(f"{len(warnings)} warning(s) - review before committing/releasing.")
    else:
        print("All clear: SBOM matches reality, nothing to update, no known vulnerabilities.")
    return 1 if (strict and warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
