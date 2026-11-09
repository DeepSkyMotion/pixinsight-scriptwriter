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
def load_config(target=None):
    if not os.path.exists(CONFIG_PATH):
        die("no config at %s. Run: psw.py init --author \"Name\" --category \"MenuCategory\" "
            "[--repo owner/name --method git|browser|none]" % CONFIG_PATH, 3)
    with open(CONFIG_PATH, encoding="utf-8") as f:
        c = json.load(f)
    # Optional two-stage setup: "targets": {"dev": {...}, "release": {...}}.
    # Each target may override menu_category, id_prefix, publish and mirror.
    # Scaffolding/testing/dev packages use "dev"; `release` publishes to "release".
    c["_target"] = ""
    if c.get("targets"):
        name = target or "dev"
        if name not in c["targets"]:
            die("unknown target %r (config has: %s)" % (name, ", ".join(c["targets"])))
        for k, v in c["targets"][name].items():
            c[k] = v
        c["_target"] = name
    elif target and target not in ("default", "dev"):
        die("this config has no targets; '--target %s' is not available" % target)
    for k in ("workspace", "mirror", "pixinsight_bin"):
        if c.get(k):
            c[k] = os.path.expanduser(c[k])
    if os.environ.get("PSW_WORKSPACE_OVERRIDE"):
        c["workspace"] = os.environ["PSW_WORKSPACE_OVERRIDE"]
    c.setdefault("optimize", "lossless")
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
            "remote_url": a.remote or "",
        },
        "mirror": a.mirror or ("~/PixInsightScripts/%s_repo" % slug if method != "none" else ""),
        "optimize": "lossless",
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
    c = load_config(getattr(a, "target", None))
    print(CONFIG_PATH)
    print(json.dumps({k: v for k, v in c.items() if not k.startswith("_")}, indent=2))
    if c.get("targets"):
        for name in c["targets"]:
            t = load_config(name)
            print("target %-8s menu 'Script > %s'  method %s  repo %s" % (
                name, t["menu_category"], t["publish"]["method"], t["publish"].get("repo")))
            if t["publish"]["method"] != "none":
                print("  PixInsight repository URL:", repo_raw_url(t))
    elif c["publish"]["method"] != "none":
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
    c = load_config(getattr(a, "target", None))
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
    c = load_config(getattr(a, "target", None))
    pi = c.get("pixinsight_bin") or detect_pi()
    if not pi or not os.path.exists(pi):
        die("PixInsight executable not found (%r). Set pixinsight_bin in %s" % (pi, CONFIG_PATH))
    vd = vdir(c, a.slug, a.n)
    main_js = getattr(a, "main_js", None) or os.path.join(script_dir(c, a.slug, a.n), vname(a.slug, a.n) + ".js")
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
    br = p["branch"]
    if not os.path.isdir(os.path.join(m, ".git")):
        os.makedirs(os.path.dirname(m) or ".", exist_ok=True)
        r = subprocess.run(["git", "clone", "-q", remote_url(c), m], capture_output=True, text=True)
        if r.returncode != 0:
            die("cannot clone %s into %s: %s" % (remote_url(c), m, r.stderr.strip()))
    git(c, "fetch", "-q", "origin")
    remote_has_branch = bool(git(c, "ls-remote", "--heads", "origin", br).stdout.strip())
    if not remote_has_branch:
        # Brand-new empty repository (or new branch): start the branch locally.
        # The first publish creates it on the remote.
        has_commits = git(c, "rev-parse", "--verify", "-q", "HEAD", check=False).returncode == 0
        if has_commits:
            git(c, "checkout", "-q", "-B", br)
        else:
            git(c, "symbolic-ref", "HEAD", "refs/heads/" + br)
        return
    if p["method"] == "browser":
        git(c, "checkout", "-q", "-B", br, "origin/" + br)
        git(c, "reset", "-q", "--hard", "origin/" + br)
    else:
        if git(c, "rev-parse", "--verify", "-q", br, check=False).returncode == 0:
            git(c, "checkout", "-q", br)
        else:
            git(c, "checkout", "-q", "-b", br, "origin/" + br)
        git(c, "pull", "-q", "--ff-only", "origin", br)


def remote_url(c):
    p = c["publish"]
    return p.get("remote_url") or "https://github.com/%s.git" % p["repo"]


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


def upload_dir(c, slug):
    return os.path.join(dist_dir(c, slug), "upload" + ("-" + c["_target"] if c.get("_target") else ""))


def stage(c, slug, zpath, tree):
    st = upload_dir(c, slug)
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
    c = load_config(getattr(a, "target", None))
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
    c = load_config(getattr(a, "target", None))
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


# ---------------------------------------------------------------- two-stage: release / retire
def release_text(dev, rel, txt, slug, n):
    """Turn a dev-version source (dev category, '<Title> vN') into release form."""
    v = vname(slug, n)
    txt = txt.replace("%s_%s" % (dev["id_prefix"], v), "%s_%s" % (rel["id_prefix"], slug))
    txt = txt.replace(v, slug)
    txt = re.sub(r"(:\s*)%s(\s*>\s*[^\n]*?) v%d\b" % (re.escape(dev["menu_category"]), n),
                 lambda m: m.group(1) + rel["menu_category"] + m.group(2), txt)
    txt = re.sub(r'(#define PSW_TITLE\s+"[^"]*?) v%d"' % n, r'\1"', txt)
    txt = txt.replace('"%s/%s"' % (cat_dir(dev), slug), '"%s/%s"' % (cat_dir(rel), slug))
    txt = txt.replace("- %s script" % dev["menu_category"], "- %s script" % rel["menu_category"])
    return txt


def cmd_release(a):
    """Publish dev version N as the public release (targets.release)."""
    dev = load_config("dev")
    if not dev.get("targets") or "release" not in dev["targets"]:
        die("release needs a config with targets.dev and targets.release (use finalize otherwise)")
    rel = load_config("release")
    check_slug(a.slug)
    sd = script_dir(dev, a.slug, a.n)
    if not os.path.isdir(sd):
        die("no dev sources: " + sd)
    mirror_sync(rel)
    tree, root, plat = load_xri(rel)
    pat = re.compile(r"%s_r(\d+)\.zip" % re.escape(a.slug))
    prev = [int(m.group(1)) for m in (pat.fullmatch(p.get("fileName", "")) for p in plat.findall("package")) if m]
    if os.path.isdir(rel["mirror"]):
        prev += [int(m.group(1)) for m in (pat.fullmatch(f) for f in os.listdir(rel["mirror"])) if m]
    k = max(prev) + 1 if prev else 1
    # Build the release zip from the dev sources.
    os.makedirs(dist_dir(rel, a.slug), exist_ok=True)
    zname = "%s_r%d.zip" % (a.slug, k)
    zpath = os.path.join(dist_dir(rel, a.slug), zname)
    base = "src/scripts/%s/%s/" % (cat_dir(rel), a.slug)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for d in ("src/", "src/scripts/", "src/scripts/%s/" % cat_dir(rel), base):
            zi = zipfile.ZipInfo(d, date_time=(2020, 1, 1, 0, 0, 0))
            zi.external_attr = (0o40755 << 16) | 0x10
            z.writestr(zi, b"")
        for fn in sorted(os.listdir(sd)):
            with open(os.path.join(sd, fn), encoding="utf-8") as f:
                data = release_text(dev, rel, f.read(), a.slug, a.n)
            zi = zipfile.ZipInfo(base + fn.replace(vname(a.slug, a.n), a.slug), date_time=(2020, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            z.writestr(zi, data)
    with open(zpath, "rb") as f:
        raw = f.read()
    # Safety net: run vN's own test harness against the transformed release build
    # in headless PixInsight before anything is staged for publishing.
    if not a.skip_test:
        import tempfile
        tmp = tempfile.mkdtemp(prefix="psw-release-")
        try:
            with zipfile.ZipFile(zpath) as z:
                z.extractall(tmp)
            main_js = os.path.join(tmp, base, a.slug + ".js")
            r = subprocess.run([sys.executable, os.path.abspath(__file__), "test", a.slug, str(a.n),
                                "--main-js", main_js], capture_output=True, text=True)
            if r.returncode != 0:
                print(r.stdout[-4000:], r.stderr[-2000:])
                die("the RELEASE build failed its tests; nothing was staged. Fix in dev and retry.", 2)
            print("release build tested in headless PixInsight: PASS")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    sha1 = hashlib.sha1(raw).hexdigest()
    b64 = zpath + ".b64"
    with open(b64, "w") as f:
        f.write(base64.b64encode(raw).decode())
    # Index: the new release replaces any earlier release of this script.
    replaced = []
    for p in list(plat.findall("package")):
        fn = p.get("fileName", "")
        if pat.fullmatch(fn) or re.fullmatch(r"%s_(v\d+|final_v\d+)\.zip" % re.escape(a.slug), fn):
            plat.remove(p)
            replaced.append(fn)
    menu = "%s > %s" % (rel["menu_category"], a.title)
    make_package(plat, zname, sha1, a.title,
                 [a.desc, "Release %d (built from development version v%d). Menu: Script > %s." % (k, a.n, menu)],
                 remove=[base])
    st = stage(rel, a.slug, zpath, tree)
    report(rel, st, zpath, sha1, b64, len(raw), menu)
    print("release number:", k, "| replaced in index:", replaced or "nothing (first release)")
    if rel["publish"]["method"] == "git":
        print("next: psw.py publish %s --target release --message \"Release %s r%d\"" % (a.slug, a.title, k))


def cmd_retire(a):
    """Remove a script's dev versions from the dev repo index and uninstall them in PixInsight."""
    c = load_config("dev") if load_config().get("targets") else load_config()
    check_slug(a.slug)
    mirror_sync(c)
    tree, root, plat = load_xri(c)
    pat_v = re.compile(r"%s_v(\d+)\.zip" % re.escape(a.slug))
    versions, dropped = set(), []
    for p in list(plat.findall("package")):
        fn = p.get("fileName", "")
        m = pat_v.fullmatch(fn)
        if m or fn == "%s_retired.zip" % a.slug:
            plat.remove(p)
            dropped.append(fn)
            if m:
                versions.add(int(m.group(1)))
    ws = os.path.join(c["workspace"], a.slug)
    if os.path.isdir(ws):
        versions |= {int(m.group(1)) for m in (re.fullmatch(r"v(\d+)", d) for d in os.listdir(ws)) if m}
    if not versions:
        die("no dev versions of %s found" % a.slug)
    remove_dirs = ["src/scripts/%s/%s_v%d/" % (cat_dir(c), a.slug, v) for v in sorted(versions)]
    # PixInsight only deletes files through a package's <remove> list, so ship a
    # tiny cleanup package whose only payload is a note.
    os.makedirs(dist_dir(c, a.slug), exist_ok=True)
    zname = "%s_retired.zip" % a.slug
    zpath = os.path.join(dist_dir(c, a.slug), zname)
    note = "src/scripts/%s/_retired/%s.txt" % (cat_dir(c), a.slug)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        zi = zipfile.ZipInfo(note, date_time=(2020, 1, 1, 0, 0, 0))
        zi.external_attr = 0o644 << 16
        z.writestr(zi, "Development versions of %s were retired on %s.\n" % (a.slug, datetime.date.today()))
    with open(zpath, "rb") as f:
        raw = f.read()
    sha1 = hashlib.sha1(raw).hexdigest()
    with open(zpath + ".b64", "w") as f:
        f.write(base64.b64encode(raw).decode())
    make_package(plat, zname, sha1, "%s (development versions retired)" % a.slug,
                 ["Removes the development versions of %s from this PixInsight installation." % a.slug],
                 remove=remove_dirs)
    st = stage(c, a.slug, zpath, tree)
    report(c, st, zpath, sha1, zpath + ".b64", len(raw), "%s > (removed)" % c["menu_category"], retired=dropped)
    print("dev version zips that can be deleted from the dev repo after publishing:", dropped)


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
    c = load_config(getattr(a, "target", None))
    p = c["publish"]
    if p["method"] != "git":
        die("publish is only for method 'git'. For 'browser' follow reference/publishing-browser.md; "
            "for 'none' the files are already in " + os.path.dirname(xri_path(c)))
    st = upload_dir(c, a.slug)
    if not os.path.isdir(st):
        die("nothing staged; run package or finalize first")
    mirror_sync(c)
    files = sorted(os.listdir(st))
    for fn in files:
        shutil.copy(os.path.join(st, fn), os.path.join(c["mirror"], fn))
    git(c, "add", *files)
    msg = a.message or ("Update %s" % a.slug)
    ident = []
    if not git(c, "config", "user.email", check=False).stdout.strip():
        # No git identity on this machine: sign the commit as the configured author.
        handle = (p["repo"].split("/")[0] if p.get("repo") else re.sub(r"\W", "", c["author"])) or "author"
        ident = ["-c", "user.name=" + c["author"], "-c", "user.email=%s@users.noreply.github.com" % handle]
    r = subprocess.run(["git", "-C", c["mirror"]] + ident + ["commit", "-q", "-m", msg],
                       capture_output=True, text=True)
    if r.returncode != 0 and "nothing to commit" not in (r.stdout + r.stderr):
        die("git commit failed: " + (r.stderr or r.stdout).strip())
    r = git(c, "push", "-q", "-u", "origin", p["branch"], check=False)
    if r.returncode != 0:
        die("git push failed. Check that this machine can push to %s (gh auth login, SSH key or "
            "credential helper). git said: %s" % (remote_url(c), r.stderr.strip()))
    print("pushed:", files, "->", p["repo"] or remote_url(c), p["branch"])
    print("verify:", [repo_raw_url(c) + f for f in files])


# ---------------------------------------------------------------- onboarding helpers
DECLINED_MARK = os.path.join(os.path.dirname(CONFIG_PATH), ".setup-declined")


def which(cmd):
    return shutil.which(cmd) or ""


def cmd_doctor(a):
    """Environment check for the setup flow. Prints JSON, never fails."""
    out = {"config_path": CONFIG_PATH, "config_exists": os.path.exists(CONFIG_PATH),
           "python": sys.version.split()[0], "git": which("git"), "gh": which("gh"),
           "pixinsight_bin": "", "platform": platform.system()}
    c = None
    if out["config_exists"]:
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                c = json.load(f)
        except Exception as e:
            out["config_error"] = str(e)
    pi = (c or {}).get("pixinsight_bin") or detect_pi()
    out["pixinsight_bin"] = pi if pi and os.path.exists(pi) else ""
    if out["gh"]:
        r = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
        out["gh_authenticated"] = r.returncode == 0
    def check_repo(pub):
        url = pub.get("remote_url") or "https://github.com/%s.git" % pub["repo"]
        r = subprocess.run(["git", "ls-remote", url], capture_output=True, text=True, timeout=60)
        return {"repo": pub.get("repo"), "repo_reachable": r.returncode == 0,
                "repo_empty": r.returncode == 0 and not r.stdout.strip(),
                "pixinsight_repository_url": "https://raw.githubusercontent.com/%s/%s/" % (pub.get("repo"), pub.get("branch", "main"))}
    if c and c.get("targets"):
        out["targets"] = {n: check_repo(t["publish"]) for n, t in c["targets"].items()
                          if t.get("publish", {}).get("method") in ("git", "browser")}
    elif c and c.get("publish", {}).get("method") in ("git", "browser"):
        out.update(check_repo(c["publish"]))
    print(json.dumps(out, indent=2))


def cmd_hook_session_start(a):
    """SessionStart hook: nudge Claude to offer setup until configured or declined."""
    try:
        if os.path.exists(CONFIG_PATH) or os.path.exists(DECLINED_MARK):
            return
        msg = ("The pixinsight-scriptwriter plugin is installed but not configured yet. "
               "At a natural moment early in this conversation, briefly tell the user (in their language) "
               "that it is ready to set up and offer to do it now: they can say yes or run "
               "/pixinsight-scriptwriter:setup. Offer once; do not interrupt an unrelated task. "
               "If they decline for good, run: python3 \"%s\" decline-setup" % os.path.abspath(__file__))
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                 "additionalContext": msg}}))
    except Exception:
        pass


def _logs(c, slug, n):
    d = os.path.join(vdir(c, slug, n), "test-logs")
    if not os.path.isdir(d):
        return []
    return sorted(os.path.join(d, f) for f in os.listdir(d) if re.fullmatch(r"\d{8}-\d{6}\.json", f))


def cmd_compare(a):
    """Prove an optimization is lossless: compare fingerprints/timings of two test runs."""
    c = load_config(getattr(a, "target", None))
    if a.baseline:
        base = a.baseline
    elif a.against_version:
        prev = _logs(c, a.slug, a.against_version)
        if not prev:
            die("no test logs for v%d" % a.against_version)
        base = prev[-1]
    else:
        cur = _logs(c, a.slug, a.n)
        if len(cur) < 2:
            die("need two test runs of v%d (or --against-version / --baseline)" % a.n)
        base = cur[-2]
    cur = _logs(c, a.slug, a.n)
    if not cur:
        die("no test logs for v%d" % a.n)
    new = cur[-1]
    with open(base) as f:
        b = json.load(f)
    with open(new) as f:
        n = json.load(f)
    fb, fn = b.get("fingerprints", {}), n.get("fingerprints", {})
    keys = sorted(set(fb) | set(fn))
    same = bool(keys) and all(fb.get(k) == fn.get(k) for k in keys)
    print("baseline:", base)
    print("current: ", new)
    for k in keys:
        print("  %-16s %s" % (k, "IDENTICAL" if fb.get(k) == fn.get(k) else "DIFFERENT"))
        if fb.get(k) != fn.get(k):
            print("     before:", fb.get(k))
            print("     after: ", fn.get(k))
    for k in sorted(set(b.get("timings_ms", {})) | set(n.get("timings_ms", {}))):
        tb, tn = b.get("timings_ms", {}).get(k), n.get("timings_ms", {}).get(k)
        if tb and tn:
            print("  time %-11s %d ms -> %d ms (%+.0f%%)" % (k, tb, tn, (tn - tb) * 100.0 / tb))
    print("OUTPUT:", "IDENTICAL (lossless)" if same else "CHANGED")
    sys.exit(0 if same else 2)


def cmd_selftest(a):
    """Scaffold a throwaway script in a temp workspace and run it in headless PixInsight."""
    import tempfile
    load_config()
    tmp = tempfile.mkdtemp(prefix="psw-selftest-")
    env = dict(os.environ, PSW_WORKSPACE_OVERRIDE=tmp)
    me = [sys.executable, os.path.abspath(__file__)]
    try:
        r = subprocess.run(me + ["new", "PswSelfTest", "1", "--title", "PSW Self Test"],
                           env=env, capture_output=True, text=True)
        if r.returncode != 0:
            die("scaffold failed: " + r.stderr.strip())
        r = subprocess.run(me + ["test", "PswSelfTest", "1", "--timeout", str(a.timeout)],
                           env=env, capture_output=True, text=True)
        print(r.stdout[-3000:])
        if r.returncode != 0:
            print(r.stderr[-2000:])
            die("SELFTEST FAILED: PixInsight could not run the template script headlessly.", 2)
        print("SELFTEST PASSED: PixInsight runs scripts headlessly on this machine.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def cmd_decline_setup(a):
    os.makedirs(os.path.dirname(DECLINED_MARK), exist_ok=True)
    with open(DECLINED_MARK, "w") as f:
        f.write(datetime.datetime.now().isoformat() + "\n")
    print("Setup reminders disabled. Remove %s to enable them again." % DECLINED_MARK)


def cmd_status(a):
    c = load_config(getattr(a, "target", None))
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


# ---------------------------------------------------------------- lint (zero-token rule check)
LINT_GUI_WORDS = r"\b(Dialog|Label|PushButton|NumericControl|CheckBox|ComboBox|Sizer|HorizontalSizer|VerticalSizer|GroupBox|MessageBox)\b"
OLD_ENUM = r"\b(StdButton|StdIcon|DataType|FrameStyle|TextAlign|TextAlignment|UndoFlag|Interpolation|ImageOp|FocusStyle|ColorSpace|SampleType)_[A-Z]\w*"


def lint_files(c, slug, n, extra=None):
    """Return (errors, warnings) for the hard rules in reference/pjsr-guide.md."""
    sd = script_dir(c, slug, n)
    v = vname(slug, n)
    files = {"main": os.path.join(sd, v + ".js"), "engine": os.path.join(sd, v + "Engine.js"),
             "gui": os.path.join(sd, v + "GUI.js")}
    if extra:
        files.update(extra)
    errs, warns = [], []
    text = {}
    for k, p in files.items():
        if not os.path.exists(p):
            errs.append("%s: missing file %s" % (k, p))
            continue
        with open(p, encoding="utf-8") as f:
            text[k] = f.read()
    for k, t in text.items():
        name = os.path.basename(files[k])
        for i, line in enumerate(t.splitlines(), 1):
            loc = "%s:%d" % (name, i)
            if re.match(r"\s*#include\s*<pjsr/.*\.jsh>", line):
                errs.append("%s pjsr .jsh include (V8 has these built in; SyntaxError)" % loc)
            m = re.search(r"//.*", line)
            if m and "/*" in m.group(0):
                errs.append("%s '/*' inside a // comment opens a block comment" % loc)
            if re.search(OLD_ENUM, line) and not line.lstrip().startswith("//"):
                errs.append("%s old-style enum %s (use Namespace.Value)" % (loc, re.search(OLD_ENUM, line).group(0)))
            if re.search(r"__[A-Z]{3,}__", line) and k != "harness":
                errs.append("%s leftover template placeholder" % loc)
            if k in ("engine", "main", "gui") and re.search(r"\.(sample|setSample)\s*\(", line):
                warns.append("%s per-pixel sample()/setSample(): prefer a process or getSamples/setSamples" % loc)
            if k == "harness" and re.search(r"\bgauss\s*\(|Math\.random", line) and not line.lstrip().startswith("//"):
                errs.append("%s non-deterministic test data (breaks lossless fingerprints)" % loc)
    m = text.get("main", "")
    if m:
        first = [l for l in m.splitlines() if l.strip().startswith("#")]
        if not first or not first[0].strip().startswith("#engine v8"):
            errs.append("main: '#engine v8' must be the first directive")
        if not re.search(r"#ifndef\s+PSW_TEST_MODE\s*\n\s*main\(\);\s*\n\s*#endif", m):
            errs.append("main: missing '#ifndef PSW_TEST_MODE / main(); / #endif' guard")
        if not re.search(r"^#feature-id\s+\S+\s*:\s*.+>\s*.+$", m, re.M):
            errs.append("main: missing or malformed '#feature-id <id> : <Category> > <Title>'")
    g = text.get("gui", "")
    if g and not re.search(r"class\s+extends\s+Dialog", g):
        errs.append("gui: dialog must be 'var PSWDialog = class extends Dialog'")
    e = text.get("engine", "")
    if e:
        if "PSWEngine" not in e or "PSWParameters" not in e:
            errs.append("engine: must define PSWParameters and PSWEngine.run(view, params)")
        code = "\n".join(l for l in e.splitlines() if not l.lstrip().startswith("//"))
        if re.search(r"\bnew\s+" + LINT_GUI_WORDS, code):
            errs.append("engine: GUI objects are not allowed in the engine file")
    return errs, warns


def cmd_lint(a):
    c = load_config(getattr(a, "target", None))
    extra = {}
    h = os.path.join(vdir(c, a.slug, a.n), "test_%s.js" % vname(a.slug, a.n))
    if os.path.exists(h):
        extra["harness"] = h
    errs, warns = lint_files(c, a.slug, a.n, extra)
    for w in warns:
        print("WARN ", w)
    for e in errs:
        print("ERROR", e)
    print("LINT:", "PASS" if not errs else "FAIL (%d errors)" % len(errs), "|", len(warns), "warnings")
    sys.exit(0 if not errs else 2)


# ---------------------------------------------------------------- learned rules (survive plugin updates)
LEARNED = os.path.join(os.path.dirname(CONFIG_PATH), "learned-rules.md")


def cmd_learn(a):
    rule = " ".join(a.rule).strip()
    if len(rule) < 10:
        die("rule text too short")
    os.makedirs(os.path.dirname(LEARNED), exist_ok=True)
    existing = open(LEARNED, encoding="utf-8").read() if os.path.exists(LEARNED) else ""
    if rule.lower() in existing.lower():
        print("already known:", rule)
        return
    if not existing:
        existing = "# Learned PixInsight/PJSR rules\n\nAdded by the pixinsight-scriptwriter lead after real test failures. Read together with reference/pjsr-guide.md.\n\n"
    with open(LEARNED, "w", encoding="utf-8") as f:
        f.write(existing + "- (%s) %s\n" % (datetime.date.today(), rule))
    print("learned:", rule)


def cmd_rules(a):
    if os.path.exists(LEARNED):
        print(open(LEARNED, encoding="utf-8").read())
    else:
        print("(no learned rules yet)")


# ---------------------------------------------------------------- browser relay (no base64 through the model)
def cmd_relay(a):
    """Serve the files to upload as one local page that stores them in window.name.

    The lead opens http://127.0.0.1:<port>/relay.html in the built-in browser, then
    navigates the SAME tab to the GitHub upload page; window.name survives that
    navigation, so a short fixed snippet can fill the upload form. The model never
    reads or writes the file contents. Exits after serving once or on timeout.
    """
    import http.server, socketserver, tempfile
    files = {}
    if a.slug:
        c = load_config(getattr(a, "target", None))
        st = upload_dir(c, a.slug)
        if not os.path.isdir(st):
            die("nothing staged for %s; run package/release/retire first" % a.slug)
        for fn in sorted(os.listdir(st)):
            with open(os.path.join(st, fn), "rb") as f:
                files[fn] = base64.b64encode(f.read()).decode()
    for p in a.path or []:
        root = os.path.abspath(a.root or (p if os.path.isdir(p) else os.path.dirname(p)))
        walk = [os.path.join(d, f) for d, _, fs in os.walk(p) for f in fs] if os.path.isdir(p) else [p]
        for fp in walk:
            rel = os.path.relpath(os.path.abspath(fp), root).replace(os.sep, "/")
            if "/.git/" in "/" + rel or "__pycache__" in rel or rel.endswith(".DS_Store"):
                continue
            with open(fp, "rb") as f:
                files[rel] = base64.b64encode(f.read()).decode()
    if not files:
        die("no files to relay")
    payload = json.dumps({"psw_relay": 1, "files": files})
    tmp = tempfile.mkdtemp(prefix="psw-relay-")
    with open(os.path.join(tmp, "relay.html"), "w") as f:
        f.write('<!doctype html><meta charset="utf-8"><title>psw relay ready</title>'
                '<script>window.name=%s;document.title="psw relay ready: %d files";</script>'
                % (json.dumps(payload), len(files)))
    served = {"n": 0}

    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kw):
            super().__init__(*args, directory=tmp, **kw)

        def do_GET(self):
            if self.path.split("?")[0] != "/relay.html":
                self.send_error(404)
                return
            super().do_GET()
            served["n"] += 1

        def log_message(self, *x):
            pass

    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer(("127.0.0.1", a.port), H) as s:
            s.timeout = 1
            port = s.server_address[1]
            print("RELAY READY: http://127.0.0.1:%d/relay.html (%d files: %s)" % (port, len(files), ", ".join(sorted(files))))
            sys.stdout.flush()
            t_end = datetime.datetime.now() + datetime.timedelta(seconds=a.timeout)
            while served["n"] == 0 and datetime.datetime.now() < t_end:
                s.handle_request()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("relay served" if served["n"] else "relay timed out without being opened")


def main():
    ap = argparse.ArgumentParser(description="pixinsight-scriptwriter toolkit")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("init")
    p.add_argument("--author", required=True); p.add_argument("--category", required=True)
    p.add_argument("--prefix"); p.add_argument("--repo"); p.add_argument("--branch", default="main")
    p.add_argument("--method", choices=["git", "browser", "none"], default="git")
    p.add_argument("--workspace"); p.add_argument("--mirror"); p.add_argument("--pixinsight")
    p.add_argument("--pi-range", default="1.9.4:1.9.99"); p.add_argument("--force", action="store_true")
    p.add_argument("--remote", help="git remote URL override, e.g. git@github.com:owner/repo.git")
    p = sp.add_parser("config"); p.add_argument("--target")
    sp.add_parser("doctor")
    sp.add_parser("hook-session-start")
    sp.add_parser("decline-setup")
    p = sp.add_parser("selftest"); p.add_argument("--timeout", type=int, default=300)
    p = sp.add_parser("compare"); p.add_argument("slug"); p.add_argument("n", type=int)
    p.add_argument("--against-version", type=int); p.add_argument("--baseline")
    p = sp.add_parser("new"); p.add_argument("slug"); p.add_argument("n", type=int)
    p.add_argument("--title", required=True); p.add_argument("--from-prev", action="store_true")
    p = sp.add_parser("test"); p.add_argument("slug"); p.add_argument("n", type=int)
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("--main-js", help=argparse.SUPPRESS)
    for name in ("package", "finalize", "release"):
        p = sp.add_parser(name); p.add_argument("slug"); p.add_argument("n", type=int)
        p.add_argument("--title", required=True); p.add_argument("--desc", required=True)
        if name != "release":
            p.add_argument("--target")
        else:
            p.add_argument("--skip-test", action="store_true")
    p = sp.add_parser("retire"); p.add_argument("slug")
    p = sp.add_parser("publish"); p.add_argument("slug"); p.add_argument("--message")
    p.add_argument("--target", help="dev (default) or release, for two-stage configs")
    p = sp.add_parser("status"); p.add_argument("slug", nargs="?", default=""); p.add_argument("--target")
    p = sp.add_parser("lint"); p.add_argument("slug"); p.add_argument("n", type=int); p.add_argument("--target")
    p = sp.add_parser("learn"); p.add_argument("rule", nargs="+")
    sp.add_parser("rules")
    p = sp.add_parser("relay"); p.add_argument("--slug"); p.add_argument("--target")
    p.add_argument("--path", action="append", help="file or directory to relay (repeatable)")
    p.add_argument("--root", help="paths are made relative to this directory")
    p.add_argument("--port", type=int, default=0, help="0 = pick a free port"); p.add_argument("--timeout", type=int, default=600)
    a = ap.parse_args()
    {"init": cmd_init, "config": cmd_config, "new": cmd_new, "test": cmd_test,
     "package": cmd_package, "finalize": cmd_finalize, "publish": cmd_publish,
     "status": cmd_status, "doctor": cmd_doctor, "hook-session-start": cmd_hook_session_start,
     "decline-setup": cmd_decline_setup, "selftest": cmd_selftest, "compare": cmd_compare,
     "release": cmd_release, "retire": cmd_retire, "lint": cmd_lint, "learn": cmd_learn,
     "rules": cmd_rules, "relay": cmd_relay}[a.cmd](a)


if __name__ == "__main__":
    main()
