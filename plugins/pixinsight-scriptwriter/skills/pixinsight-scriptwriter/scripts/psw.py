#!/usr/bin/env python3
"""pixinsight-scriptwriter toolkit: scaffold, test, package and publish PixInsight (PJSR) scripts.

Subcommands
  init      --author A --category C [--repo owner/name] [--method git|browser|none] ...
                                                     create the user config (first run)
  config                                             print the current config
  new       <Slug> <N> --title "Title" [--from-prev] scaffold version N
  test      <Slug> <N> [--timeout 300]               run in a separate headless PixInsight
  package   <Slug> <N> --title T --desc D            build zip + updated updates.xri
  finalize  <Slug> <N> --title T --desc D            final release that retires vN packages
  publish   <Slug>                                   method=git: commit + push the staged files
  status    [<Slug>]                                 versions in workspace and in updates.xri

Config file: $PSW_CONFIG or ~/.config/pixinsight-scriptwriter/config.json
Python 3.8+, standard library only. Works on macOS, Linux and Windows.
"""
import argparse, base64, datetime, hashlib, json, os, platform, re, shutil, subprocess, sys, zipfile
import xml.etree.ElementTree as ET

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(SKILL, "templates")
CONFIG_PATH = os.environ.get("PSW_CONFIG") or os.path.join(
    os.path.expanduser("~"), ".config", "pixinsight-scriptwriter", "config.json")

PI_CANDIDATES = {
    "Darwin": ["/Applications/PixInsight/PixInsight.app/Contents/MacOS/PixInsight"],
    "Linux": ["/opt/PixInsight/bin/PixInsight", "/opt/PixInsight/bin/PixInsight.sh"],
    "Windows": [r"C:\Program Files\PixInsight\bin\PixInsight.exe"],
}


def die(msg, code=1):
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------- config
def load_config():
    if not os.path.exists(CONFIG_PATH):
        die("no config at %s. Run: psw.py init --author \"Name\" --category \"MenuCategory\" "
            "[--repo owner/name --method git|browser|none]" % CONFIG_PATH, 3)
    with open(CONFIG_PATH, encoding="utf-8") as f:
        c = json.load(f)
    for k in ("workspace", "mirror", "pixinsight_bin"):
        if c.get(k):
            c[k] = os.path.expanduser(c[k])
    return c


def detect_pi():
    for p in PI_CANDIDATES.get(platform.system(), []):
        if os.path.exists(p):
            return p
    return ""


def cmd_init(a):
    if os.path.exists(CONFIG_PATH) and not a.force:
        die("config already exists at %s (use --force to overwrite)" % CONFIG_PATH)
    cat = a.category.strip()
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9 _-]{1,40}", cat):
        die("category must be 2-41 chars of letters, digits, space, _ or -, starting with a letter")
    prefix = a.prefix or (re.sub(r"[^A-Za-z0-9]", "", cat)[:12] or "PSW")
    method = a.method
    if method in ("git", "browser") and not a.repo:
        die("--repo owner/name is required for method " + method)
    slug = re.sub(r"[^A-Za-z0-9]", "", cat) or "PixInsight"
    c = {
        "author": a.author.strip(),
        "menu_category": cat,
        "id_prefix": prefix,
        "workspace": a.workspace or "~/PixInsightScripts/%s_work" % slug,
        "pixinsight_bin": a.pixinsight or detect_pi(),
        "pixinsight_version_range": a.pi_range,
        "publish": {
            "method": method,
            "repo": a.repo or "",
            "branch": a.branch,
        },
        "mirror": a.mirror or ("~/PixInsightScripts/%s_repo" % slug if method != "none" else ""),
    }
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(c, f, indent=2)
    print("config written:", CONFIG_PATH)
    print(json.dumps(c, indent=2))
    if not c["pixinsight_bin"]:
        print("WARNING: PixInsight executable not found; set pixinsight_bin in the config.")
    if method != "none":
        print("repository URL to add in PixInsight (Resources > Updates > Manage Repositories):")
        print("  " + repo_raw_url(c))


def cmd_config(a):
    c = load_config()
    print(CONFIG_PATH)
    print(json.dumps(c, indent=2))
    if c["publish"]["method"] != "none":
        print("PixInsight repository URL:", repo_raw_url(c))


def repo_raw_url(c):
    p = c["publish"]
    return "https://raw.githubusercontent.com/%s/%s/" % (p["repo"], p["branch"])


# ---------------------------------------------------------------- paths
def check_slug(slug):
    if not re.fullmatch(r"[A-Z][A-Za-z0-9]{2,40}", slug):
        die("slug must be PascalCase ASCII letters/digits, e.g. StarHaloReducer")


def vname(slug, n):
    return "%s_v%d" % (slug, n)


def vdir(c, slug, n):
    return os.path.join(c["workspace"], slug, "v%d" % n)


def cat_dir(c):
    return re.sub(r"[^A-Za-z0-9_-]", "", c["menu_category"].replace(" ", "")) or "Scripts"


def script_dir(c, slug, n):
    return os.path.join(vdir(c, slug, n), "src", "scripts", cat_dir(c), vname(slug, n))


def dist_dir(c, slug):
    return os.path.join(c["workspace"], slug, "dist")


# ---------------------------------------------------------------- new
def cmd_new(a):
    c = load_config()
    check_slug(a.slug)
    dst = script_dir(c, a.slug, a.n)
    if os.path.exists(dst):
        die("already exists: " + dst)
    os.makedirs(dst)
    today = datetime.date.today()
    if a.from_prev:
        prev = a.n - 1
        src = script_dir(c, a.slug, prev)
        if not os.path.isdir(src):
            die("previous version not found: " + src)
        old, new = vname(a.slug, prev), vname(a.slug, a.n)
        for fn in os.listdir(src):
            with open(os.path.join(src, fn), encoding="utf-8") as f:
                txt = f.read()
            txt = txt.replace(old, new)
            txt = re.sub(r"\bv%d\b" % prev, "v%d" % a.n, txt)
            txt = re.sub(r'#define PSW_VERSION\s+"%d"' % prev, '#define PSW_VERSION  "%d"' % a.n, txt)
            txt = re.sub(r"Version %d - Released [0-9-]+" % prev, "Version %d - Released %s" % (a.n, today), txt)
            with open(os.path.join(dst, fn.replace(old, new)), "w", encoding="utf-8") as f:
                f.write(txt)
        prev_test = os.path.join(vdir(c, a.slug, prev), "test_%s.js" % old)
        if os.path.exists(prev_test):
            with open(prev_test, encoding="utf-8") as f:
                t = f.read().replace(old, new)
            with open(os.path.join(vdir(c, a.slug, a.n), "test_%s.js" % new), "w", encoding="utf-8") as f:
                f.write(t)
    else:
        rep = [("__PREFIX__", c["id_prefix"]), ("__SLUG__", a.slug), ("__TITLE__", a.title),
               ("__N__", str(a.n)), ("__DATE__", str(today)), ("__YEAR__", str(today.year)),
               ("__CATEGORY__", c["menu_category"]), ("__CATDIR__", cat_dir(c)), ("__AUTHOR__", c["author"])]
        for tpl, out in (("Script.js", "%s.js"), ("ScriptEngine.js", "%sEngine.js"), ("ScriptGUI.js", "%sGUI.js")):
            with open(os.path.join(TEMPLATES, tpl), encoding="utf-8") as f:
                txt = f.read()
            for k, v in rep:
                txt = txt.replace(k, v)
            with open(os.path.join(dst, out % vname(a.slug, a.n)), "w", encoding="utf-8") as f:
                f.write(txt)
        shutil.copy(os.path.join(TEMPLATES, "TestHarness.js"),
                    os.path.join(vdir(c, a.slug, a.n), "test_%s.js" % vname(a.slug, a.n)))
    print("scaffolded:", dst)
    for fn in sorted(os.listdir(dst)):
        print("  ", os.path.join(dst, fn))
    print("test harness:", os.path.join(vdir(c, a.slug, a.n), "test_%s.js" % vname(a.slug, a.n)))


# ---------------------------------------------------------------- test
def js_path(p):
    return p.replace("\\", "/")


def cmd_test(a):
    c = load_config()
    pi = c.get("pixinsight_bin") or detect_pi()
    if not pi or not os.path.exists(pi):
        die("PixInsight executable not found (%r). Set pixinsight_bin in %s" % (pi, CONFIG_PATH))
    vd = vdir(c, a.slug, a.n)
    main_js = os.path.join(script_dir(c, a.slug, a.n), vname(a.slug, a.n) + ".js")
    harness_src = os.path.join(vd, "test_%s.js" % vname(a.slug, a.n))
    for p in (main_js, harness_src):
        if not os.path.exists(p):
            die("missing " + p)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    logs = os.path.join(vd, "test-logs")
    os.makedirs(logs, exist_ok=True)
    log_json = os.path.join(logs, stamp + ".json")
    log_out = os.path.join(logs, stamp + ".console.txt")
    with open(harness_src, encoding="utf-8") as f:
        h = f.read().replace("__SCRIPT_PATH__", js_path(main_js)).replace("__LOG_PATH__", js_path(log_json))
    run_js = os.path.join(logs, stamp + ".run.js")
    with open(run_js, "w", encoding="utf-8") as f:
        f.write(h)
    # PixInsight writes errors only to its Process Console, so wrap the run
    # with console.beginLog()/endLog() to capture them into a text file.
    begin_js = os.path.join(logs, stamp + ".begin.js")
    end_js = os.path.join(logs, stamp + ".end.js")
    with open(begin_js, "w") as f:
        f.write('#engine v8\nconsole.beginLog("%s");\n' % js_path(log_out))
    with open(end_js, "w") as f:
        f.write("#engine v8\nconsole.endLog();\n")
    cmd = [pi, "-n", "--automation-mode", "--no-startup-scripts",
           "-r=" + begin_js, "-r=" + run_js, "-r=" + end_js, "--force-exit"]
    try:
        rc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            timeout=a.timeout).returncode
    except subprocess.TimeoutExpired:
        if platform.system() != "Windows":
            subprocess.run(["pkill", "-f", run_js])
        die("TIMEOUT after %ds (a modal dialog or an endless loop?). console: %s" % (a.timeout, log_out))
    console = open(log_out, errors="replace").read() if os.path.exists(log_out) else ""
    console = re.sub(r"^\[[0-9: -]+\] ?", "", console, flags=re.M)
    for marker in ("Processing script file: " + run_js, "Processing script file: " + js_path(run_js)):
        if marker in console:
            console = console.split(marker, 1)[1].split("Processing script file:", 1)[0]
            break
    lines = [l for l in console.splitlines() if l.strip() and not l.startswith("run -x=")]
    print("pixinsight exit code:", rc)
    if lines:
        print("PixInsight console during the test:")
        print("\n".join("  " + l for l in lines[-80:]))
    if not os.path.exists(log_json):
        die("no result log written -> the script failed to parse or crashed at load time. "
            "See the PixInsight console above (the 'file, line N' it names is the culprit).", 2)
    with open(log_json) as f:
        res = json.load(f)
    print(json.dumps(res, indent=2))
    print("RESULT:", "PASS" if res.get("ok") else "FAIL")
    sys.exit(0 if res.get("ok") else 2)


# ---------------------------------------------------------------- repository index
def git(c, *args, check=True):
    return subprocess.run(["git", "-C", c["mirror"]] + list(args), check=check,
                          capture_output=True, text=True)


def mirror_sync(c):
    p = c["publish"]
    if p["method"] == "none":
        os.makedirs(c["workspace"], exist_ok=True)
        return
    m = c["mirror"]
    if not os.path.isdir(os.path.join(m, ".git")):
        os.makedirs(os.path.dirname(m) or ".", exist_ok=True)
        r = subprocess.run(["git", "clone", "-q", "https://github.com/%s.git" % p["repo"], m],
                           capture_output=True, text=True)
        if r.returncode != 0:
            die("cannot clone %s into %s: %s" % (p["repo"], m, r.stderr.strip()))
    git(c, "fetch", "-q", "origin")
    if p["method"] == "browser":
        git(c, "reset", "-q", "--hard", "origin/" + p["branch"])
    else:
        git(c, "checkout", "-q", p["branch"])
        git(c, "pull", "-q", "--ff-only", "origin", p["branch"])


def xri_path(c):
    if c["publish"]["method"] == "none":
        return os.path.join(c["workspace"], "repository", "updates.xri")
    return os.path.join(c["mirror"], "updates.xri")


def load_xri(c):
    path = xri_path(c)
    if os.path.exists(path):
        tree = ET.parse(path)
        root = tree.getroot()
    else:
        root = ET.Element("xri", {"version": "1.0"})
        d = ET.SubElement(root, "description")
        p = ET.SubElement(d, "p")
        p.text = "%s - PixInsight scripts by %s." % (c["menu_category"], c["author"])
        tree = ET.ElementTree(root)
    rng = c.get("pixinsight_version_range", "1.9.4:1.9.99")
    plat = None
    for p in root.findall("platform"):
        if p.get("version") == rng:
            plat = p
    if plat is None:
        plat = ET.SubElement(root, "platform", {"os": "all", "arch": "noarch", "version": rng})
    return tree, root, plat


def make_package(plat, filename, sha1, title, desc_paras, remove=None):
    for old in plat.findall("package"):
        if old.get("fileName") == filename:
            plat.remove(old)
    pkg = ET.SubElement(plat, "package", {"fileName": filename, "sha1": sha1, "type": "script",
                                          "releaseDate": datetime.date.today().strftime("%Y%m%d")})
    t = ET.SubElement(pkg, "title")
    t.text = title
    if remove:
        r = ET.SubElement(pkg, "remove")
        r.text = "\n".join(remove)
    d = ET.SubElement(pkg, "description")
    for para in desc_paras:
        p = ET.SubElement(d, "p")
        p.text = para


def write_xri(tree, out_path):
    if hasattr(ET, "indent"):
        ET.indent(tree, space="   ")
    body = ET.tostring(tree.getroot(), encoding="unicode")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n")


def finalize_text(c, txt, slug, n):
    txt = txt.replace(vname(slug, n), slug)
    txt = re.sub(r"(%s > [^\n]*?) v%d\b" % (re.escape(c["menu_category"]), n), r"\1", txt)
    txt = re.sub(r'(#define PSW_TITLE\s+"[^"]*?) v%d"' % n, r'\1"', txt)
    return txt


def build_zip(c, slug, n, final=False):
    sd = script_dir(c, slug, n)
    if not os.path.isdir(sd):
        die("no sources: " + sd)
    os.makedirs(dist_dir(c, slug), exist_ok=True)
    name = slug if final else vname(slug, n)
    zname = ("%s_final_v%d.zip" % (slug, n)) if final else (name + ".zip")
    zpath = os.path.join(dist_dir(c, slug), zname)
    base = "src/scripts/%s/%s/" % (cat_dir(c), name)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for d in ("src/", "src/scripts/", "src/scripts/%s/" % cat_dir(c), base):
            zi = zipfile.ZipInfo(d, date_time=(2020, 1, 1, 0, 0, 0))
            zi.external_attr = (0o40755 << 16) | 0x10
            z.writestr(zi, b"")
        for fn in sorted(os.listdir(sd)):
            with open(os.path.join(sd, fn), encoding="utf-8") as f:
                data = f.read()
            if final:
                data = finalize_text(c, data, slug, n)
                fn = fn.replace(vname(slug, n), slug)
            zi = zipfile.ZipInfo(base + fn, date_time=(2020, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            z.writestr(zi, data)
    with open(zpath, "rb") as f:
        raw = f.read()
    sha1 = hashlib.sha1(raw).hexdigest()
    b64 = zpath + ".b64"
    with open(b64, "w") as f:
        f.write(base64.b64encode(raw).decode())
    return zpath, sha1, b64, len(raw)


def stage(c, slug, zpath, tree):
    st = os.path.join(dist_dir(c, slug), "upload")
    shutil.rmtree(st, ignore_errors=True)
    os.makedirs(st)
    shutil.copy(zpath, st)
    write_xri(tree, os.path.join(st, "updates.xri"))
    if c["publish"]["method"] == "none":
        repo = os.path.dirname(xri_path(c))
        os.makedirs(repo, exist_ok=True)
        shutil.copy(zpath, repo)
        shutil.copy(os.path.join(st, "updates.xri"), repo)
    return st


def cmd_package(a):
    c = load_config()
    check_slug(a.slug)
    mirror_sync(c)
    zpath, sha1, b64, size = build_zip(c, a.slug, a.n)
    tree, root, plat = load_xri(c)
    menu = "%s > %s v%d" % (c["menu_category"], a.title, a.n)
    make_package(plat, os.path.basename(zpath), sha1, "%s v%d" % (a.title, a.n),
                 [a.desc, "Menu: Script > %s." % menu])
    st = stage(c, a.slug, zpath, tree)
    report(c, st, zpath, sha1, b64, size, menu)


def cmd_finalize(a):
    c = load_config()
    check_slug(a.slug)
    mirror_sync(c)
    zpath, sha1, b64, size = build_zip(c, a.slug, a.n, final=True)
    tree, root, plat = load_xri(c)
    removed_pkgs, versions = [], set()
    pat_v = re.compile(r"%s_v(\d+)\.zip" % re.escape(a.slug))
    pat_f = re.compile(r"%s_final_v\d+\.zip" % re.escape(a.slug))
    for pkg in list(plat.findall("package")):
        fn = pkg.get("fileName", "")
        m = pat_v.fullmatch(fn)
        if m or pat_f.fullmatch(fn):
            plat.remove(pkg)
            removed_pkgs.append(fn)
            if m:
                versions.add(int(m.group(1)))
    ws = os.path.join(c["workspace"], a.slug)
    for d in os.listdir(ws):
        m = re.fullmatch(r"v(\d+)", d)
        if m:
            versions.add(int(m.group(1)))
    remove_dirs = ["src/scripts/%s/%s_v%d/" % (cat_dir(c), a.slug, v) for v in sorted(versions)]
    remove_dirs.append("src/scripts/%s/%s/" % (cat_dir(c), a.slug))
    menu = "%s > %s" % (c["menu_category"], a.title)
    make_package(plat, os.path.basename(zpath), sha1, a.title,
                 [a.desc, "Final release (from v%d). Menu: Script > %s." % (a.n, menu)],
                 remove=remove_dirs)
    st = stage(c, a.slug, zpath, tree)
    report(c, st, zpath, sha1, b64, size, menu, retired=removed_pkgs)


def report(c, st, zpath, sha1, b64, size, menu, retired=None):
    out = {
        "publish_method": c["publish"]["method"],
        "upload_dir": st,
        "upload_files": sorted(os.listdir(st)),
        "zip": zpath, "zip_size": size, "sha1": sha1, "zip_base64_file": b64,
        "menu": "Script > " + menu,
        "xri_preview": open(os.path.join(st, "updates.xri"), encoding="utf-8").read(),
    }
    if c["publish"]["method"] != "none":
        base = repo_raw_url(c)
        out["verify_after_upload"] = [base + "updates.xri", base + os.path.basename(zpath)]
    else:
        out["local_repository_dir"] = os.path.dirname(xri_path(c))
    if retired is not None:
        out["retired_packages_still_in_repo"] = retired
        out["note"] = "Delete retired zips from the repository only after the user confirms."
    print(json.dumps(out, indent=2))


# ---------------------------------------------------------------- publish (git method)
def cmd_publish(a):
    c = load_config()
    p = c["publish"]
    if p["method"] != "git":
        die("publish is only for method 'git'. For 'browser' follow reference/publishing-browser.md; "
            "for 'none' the files are already in " + os.path.dirname(xri_path(c)))
    st = os.path.join(dist_dir(c, a.slug), "upload")
    if not os.path.isdir(st):
        die("nothing staged; run package or finalize first")
    mirror_sync(c)
    files = sorted(os.listdir(st))
    for fn in files:
        shutil.copy(os.path.join(st, fn), os.path.join(c["mirror"], fn))
    git(c, "add", *files)
    msg = a.message or ("Update %s" % a.slug)
    r = git(c, "commit", "-q", "-m", msg, check=False)
    if r.returncode != 0 and "nothing to commit" not in (r.stdout + r.stderr):
        die("git commit failed: " + r.stderr.strip())
    r = git(c, "push", "-q", "origin", p["branch"], check=False)
    if r.returncode != 0:
        die("git push failed (credentials?): " + r.stderr.strip())
    print("pushed:", files, "->", p["repo"], p["branch"])
    print("verify:", [repo_raw_url(c) + f for f in files])


def cmd_status(a):
    c = load_config()
    try:
        mirror_sync(c)
        tree, root, plat = load_xri(c)
        print("updates.xri packages:")
        for pk in plat.findall("package"):
            if not a.slug or pk.get("fileName", "").startswith(a.slug):
                print("  ", pk.get("fileName"), pk.get("sha1"), pk.findtext("title"))
    except SystemExit:
        raise
    except Exception as e:
        print("could not read repository index:", e)
    base = os.path.join(c["workspace"], a.slug) if a.slug else c["workspace"]
    print("workspace:", base)
    if os.path.isdir(base):
        for d in sorted(os.listdir(base)):
            print("  ", d)


def main():
    ap = argparse.ArgumentParser(description="pixinsight-scriptwriter toolkit")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("init")
    p.add_argument("--author", required=True); p.add_argument("--category", required=True)
    p.add_argument("--prefix"); p.add_argument("--repo"); p.add_argument("--branch", default="main")
    p.add_argument("--method", choices=["git", "browser", "none"], default="git")
    p.add_argument("--workspace"); p.add_argument("--mirror"); p.add_argument("--pixinsight")
    p.add_argument("--pi-range", default="1.9.4:1.9.99"); p.add_argument("--force", action="store_true")
    sp.add_parser("config")
    p = sp.add_parser("new"); p.add_argument("slug"); p.add_argument("n", type=int)
    p.add_argument("--title", required=True); p.add_argument("--from-prev", action="store_true")
    p = sp.add_parser("test"); p.add_argument("slug"); p.add_argument("n", type=int)
    p.add_argument("--timeout", type=int, default=300)
    for name in ("package", "finalize"):
        p = sp.add_parser(name); p.add_argument("slug"); p.add_argument("n", type=int)
        p.add_argument("--title", required=True); p.add_argument("--desc", required=True)
    p = sp.add_parser("publish"); p.add_argument("slug"); p.add_argument("--message")
    p = sp.add_parser("status"); p.add_argument("slug", nargs="?", default="")
    a = ap.parse_args()
    {"init": cmd_init, "config": cmd_config, "new": cmd_new, "test": cmd_test,
     "package": cmd_package, "finalize": cmd_finalize, "publish": cmd_publish,
     "status": cmd_status}[a.cmd](a)


if __name__ == "__main__":
    main()
