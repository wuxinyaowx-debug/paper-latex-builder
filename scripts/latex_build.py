#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""latex_build.py -- deterministic multi-pass LaTeX build driver (Python stdlib only).

Purpose
-------
Compile a LaTeX project the way a careful human would, but reproducibly:
  1. locate the main .tex file (or take it from --main);
  2. choose the engine (pdflatex / xelatex / lualatex) from preamble evidence;
  3. run nonstopmode passes with -file-line-error, inserting bibtex/biber
     passes when the bibliography requires them;
  4. stop when cross-references converge (aux-file hash stable and no
     "Rerun" request in the log) or --max-passes is reached;
  5. emit a machine-readable build report (JSON) recording commands,
     versions, pass count and error/warning counts, so another person can
     reproduce the exact build.

Exit codes
----------
0  build succeeded (PDF produced, no TeX errors)
1  build finished with TeX errors (see report / triage)
2  no main .tex file found
3  environment error (engine missing, project dir missing)
4  pass timed out

The script never modifies source files. All diagnostic output goes to the
report JSON and stdout; the .log files stay next to the sources.
"""

import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

ENGINES = ("pdflatex", "xelatex", "lualatex")

AUX_GLOBS = ("*.aux", "*.toc", "*.lof", "*.lot", "*.bbl", "*.bcf",
             "*.ind", "*.out", "*.nav", "*.snm")


# --------------------------------------------------------------------------
# project discovery
# --------------------------------------------------------------------------

def find_main_tex(project):
    """Return the most likely main .tex file, or None.

    Candidates contain \\documentclass. Among candidates prefer, in order:
    a file named main.tex / paper.tex / thesis.tex / <dirname>.tex, then the
    candidate that is \\input by nobody else, then the shortest path.
    """
    tex_files = []
    for path in glob.glob(os.path.join(project, "**", "*.tex"), recursive=True):
        # skip obvious build/backup dirs
        parts = set(os.path.relpath(path, project).split(os.sep))
        if parts & {".git", "node_modules", "__pycache__"}:
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                head = fh.read(65536)
        except OSError:
            continue
        if re.search(r"\\documentclass\b", head):
            tex_files.append(path)
    if not tex_files:
        return None
    if len(tex_files) == 1:
        return tex_files[0]

    preferred_names = {"main.tex", "paper.tex", "thesis.tex", "article.tex",
                       os.path.basename(os.path.abspath(project)).lower() + ".tex"}
    for path in tex_files:
        if os.path.basename(path).lower() in preferred_names:
            return path

    # a file that nobody \input/\include's is likely the root
    included = set()
    for path in tex_files:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        for m in re.finditer(r"\\(?:input|include)\s*\{([^}]+)\}", text):
            included.add(os.path.basename(m.group(1)).replace(".tex", ""))
    roots = [p for p in tex_files
             if os.path.basename(p).replace(".tex", "") not in included]
    pool = roots or tex_files
    pool.sort(key=lambda p: (len(os.path.relpath(p, project)), p))
    return pool[0]


def strip_comments(text):
    """Remove %-comments (respecting \\%) so comment text does not mislead detection."""
    out = []
    for line in text.splitlines():
        buf, i = [], 0
        while i < len(line):
            if line[i] == "%" and (i == 0 or line[i - 1] != "\\"):
                break
            buf.append(line[i])
            i += 1
        out.append("".join(buf))
    return "\n".join(out)


def choose_engine(main_tex):
    """Pick engine from source evidence. Chinese templates -> xelatex."""
    try:
        with open(main_tex, "r", encoding="utf-8", errors="replace") as fh:
            text = strip_comments(fh.read(262144))
    except OSError:
        return "pdflatex"
    if re.search(r"\\usepackage(\[[^\]]*\])?\{(fontspec|xeCJK|unicode-math)\}", text):
        return "xelatex"
    if re.search(r"\\documentclass(\[[^\]]*\])?\{[^}]*ctex", text) or \
       re.search(r"\\usepackage(\[[^\]]*\])?\{ctex\}", text):
        return "xelatex"
    if re.search(r"\\usepackage(\[[^\]]*\])?\{luacode\}", text):
        return "lualatex"
    # CJK characters in source with pdfLaTeX fonts only -> still pdflatex+CJKutf8 is
    # possible, but xelatex is the safer default when ctex is absent and CJK present.
    if re.search(r"[一-鿿]", text) and "CJKutf8" not in text:
        return "xelatex"
    return "pdflatex"


def documentclass_of(main_tex):
    try:
        with open(main_tex, "r", encoding="utf-8", errors="replace") as fh:
            text = strip_comments(fh.read(65536))
    except OSError:
        return None
    m = re.search(r"\\documentclass(?:\[[^\]]*\])?\{([^}]+)\}", text)
    return m.group(1).strip() if m else None


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def which(cmd):
    return shutil.which(cmd)


def tool_version(cmd):
    """First line of `<cmd> --version`, best effort."""
    exe = which(cmd)
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--version"], capture_output=True,
                             text=True, timeout=20, errors="replace")
        line = (out.stdout or out.stderr).splitlines()
        return line[0].strip() if line else None
    except Exception:
        return None


def kpsewhich(name):
    exe = which("kpsewhich")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, name], capture_output=True, text=True,
                             timeout=20, errors="replace")
        return out.stdout.strip() or None
    except Exception:
        return None


def aux_signature(project):
    """Hash over all aux-like files; used to detect convergence."""
    h = hashlib.sha256()
    for pattern in AUX_GLOBS:
        for path in sorted(glob.glob(os.path.join(project, "**", pattern),
                                     recursive=True)):
            try:
                with open(path, "rb") as fh:
                    h.update(os.path.basename(path).encode())
                    h.update(fh.read())
            except OSError:
                pass
    return h.hexdigest()


def count_errors_warnings(log_path):
    errors = warnings = 0
    if not log_path or not os.path.isfile(log_path):
        return errors, warnings
    fileline_err = re.compile(r"^\S[^\n:()]*\.tex:\d+: ")
    with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("! ") or fileline_err.match(line):
                errors += 1
            elif re.search(r"(LaTeX|Package|Class) .*Warning", line) or \
                    line.startswith("Overfull \\") or line.startswith("Underfull \\"):
                warnings += 1
    return errors, warnings


def log_requests_rerun(log_path):
    if not log_path or not os.path.isfile(log_path):
        return False
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return False
    return ("Rerun to get cross-references right" in text
            or "Please rerun" in text
            or "rerun LaTeX" in text)


def pages_from_log(log_path):
    if not log_path or not os.path.isfile(log_path):
        return None
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return None
    m = re.findall(r"Output written on [^\n]*\((\d+) pages?", text)
    return int(m[-1]) if m else None


def run_pass(cmd, cwd, timeout_s):
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                              timeout=timeout_s, errors="replace")
        return proc.returncode, time.time() - t0, (proc.stdout or "")[-4000:]
    except subprocess.TimeoutExpired:
        return None, time.time() - t0, "TIMEOUT after %ds" % timeout_s


# --------------------------------------------------------------------------
# main build
# --------------------------------------------------------------------------

def build(project, main, engine, max_passes, timeout_s, report_path):
    report = {
        "schema": "latex-build-report/1",
        "project": os.path.abspath(project),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "status": "failed",
        "main_tex": None,
        "documentclass": None,
        "engine": engine,
        "engine_version": None,
        "tex_distribution": None,
        "bib_tool": None,
        "passes": [],
        "converged": False,
        "aux_signature": None,
        "log": None,
        "pdf": None,
        "pdf_pages": None,
        "errors": None,
        "warnings": None,
        "notes": [],
    }

    if not os.path.isdir(project):
        report["status"] = "environment_error"
        report["notes"].append("project directory not found: %s" % project)
        _write_report(report, report_path)
        return 3

    if not main:
        main = find_main_tex(project)
        if not main:
            report["status"] = "no_main_tex"
            report["notes"].append(
                "no .tex file containing \\documentclass found under project")
            _write_report(report, report_path)
            return 2
        report["notes"].append("main tex auto-detected: %s"
                               % os.path.relpath(main, project))
    main = os.path.abspath(main)
    report["main_tex"] = main
    report["documentclass"] = documentclass_of(main)

    if engine == "auto":
        engine = choose_engine(main)
        report["notes"].append("engine auto-selected: %s" % engine)
    report["engine"] = engine

    exe = which(engine)
    if not exe:
        report["status"] = "environment_error"
        report["notes"].append(
            "engine '%s' not found on PATH; install a TeX distribution "
            "(TeX Live / MiKTeX) or use the platform latex-compiler tool" % engine)
        _write_report(report, report_path)
        return 3
    report["engine_version"] = tool_version(engine)

    cls = report["documentclass"]
    if cls:
        found = kpsewhich(cls + ".cls")
        if found:
            report["notes"].append("class file resolved: %s" % found)
        else:
            report["notes"].append(
                "WARNING: class file %s.cls NOT found by kpsewhich; "
                "build will fail unless it sits next to the sources" % cls)

    workdir = os.path.dirname(main)
    jobname = os.path.splitext(os.path.basename(main))[0]
    log_path = os.path.join(workdir, jobname + ".log")
    pdf_path = os.path.join(workdir, jobname + ".pdf")

    base_cmd = [exe, "-interaction=nonstopmode", "-file-line-error",
                "-synctex=1", os.path.basename(main)]

    prev_sig = None
    bib_done = False
    exit_code = 1

    for p in range(1, max_passes + 1):
        rc, dur, tail = run_pass(base_cmd, workdir, timeout_s)
        errs, warns = count_errors_warnings(log_path)
        report["passes"].append({
            "pass": p, "tool": engine, "cmd": " ".join(base_cmd),
            "returncode": rc, "duration_s": round(dur, 2),
            "errors_in_log": errs, "warnings_in_log": warns,
            "output_tail": tail[-1500:],
        })
        if rc is None:
            report["status"] = "timeout"
            report["notes"].append("pass %d exceeded %ds; aborting"
                                   % (p, timeout_s))
            _write_report(report, report_path)
            return 4

        # bibliography pass, once, after the first engine pass
        if not bib_done and p == 1:
            bcf = os.path.join(workdir, jobname + ".bcf")
            aux = os.path.join(workdir, jobname + ".aux")
            bib_tool = None
            if os.path.isfile(bcf) and which("biber"):
                bib_tool = "biber"
            elif os.path.isfile(aux) and which("bibtex"):
                try:
                    with open(aux, "r", encoding="utf-8", errors="replace") as fh:
                        if "\\citation" in fh.read():
                            bib_tool = "bibtex"
                except OSError:
                    pass
            if bib_tool:
                bt0 = time.time()
                brc, bdur, btail = run_pass([which(bib_tool), jobname],
                                            workdir, timeout_s)
                report["bib_tool"] = {
                    "tool": bib_tool, "returncode": brc,
                    "duration_s": round(bdur, 2), "output_tail": btail[-1500:],
                }
                bib_done = True

        sig = aux_signature(workdir)
        report["aux_signature"] = sig

        if errs > 0 and not os.path.isfile(pdf_path):
            # still try further passes: later passes sometimes unblock (e.g. bib)
            pass

        if p >= 2 and sig == prev_sig and not log_requests_rerun(log_path):
            report["converged"] = True
            break
        prev_sig = sig

    report["log"] = log_path if os.path.isfile(log_path) else None
    report["pdf"] = pdf_path if os.path.isfile(pdf_path) else None
    report["pdf_pages"] = pages_from_log(log_path)
    errs, warns = count_errors_warnings(log_path)
    report["errors"] = errs
    report["warnings"] = warns
    report["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    if os.path.isfile(pdf_path) and errs == 0:
        report["status"] = "success"
        exit_code = 0
    elif os.path.isfile(pdf_path):
        report["status"] = "errors"
        report["notes"].append(
            "PDF produced but log contains %d error lines; run latex_log_triage.py"
            % errs)
        exit_code = 1
    else:
        report["status"] = "errors"
        report["notes"].append(
            "no PDF produced; run latex_log_triage.py on the log for root causes")
        exit_code = 1

    _write_report(report, report_path)
    return exit_code


def _write_report(report, path):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    summary = {
        "status": report["status"], "engine": report["engine"],
        "passes": len(report["passes"]), "converged": report["converged"],
        "errors": report["errors"], "warnings": report["warnings"],
        "pdf": report["pdf"], "report": os.path.abspath(path),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser(description="multi-pass LaTeX build driver")
    ap.add_argument("--project", default=os.environ.get("LATEX_PROJECT", "."),
                    help="project root directory (default: cwd)")
    ap.add_argument("--main", default=None,
                    help="main .tex file (default: auto-detect)")
    ap.add_argument("--engine", default=os.environ.get("LATEX_ENGINE", "auto"),
                    choices=["auto"] + list(ENGINES),
                    help="TeX engine (default: auto)")
    ap.add_argument("--max-passes", type=int, default=4,
                    help="maximum engine passes (default: 4)")
    ap.add_argument("--timeout", type=int, default=120,
                    help="timeout per pass in seconds (default: 120)")
    ap.add_argument("--report", default="build-report.json",
                    help="path of the JSON build report")
    args = ap.parse_args()
    code = build(args.project, args.main, args.engine, args.max_passes,
                 args.timeout, args.report)
    sys.exit(code)


if __name__ == "__main__":
    main()
