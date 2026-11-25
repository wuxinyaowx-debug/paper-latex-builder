#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""latex_preflight.py -- static LaTeX source checks that need no TeX engine.

Runs in seconds before the first compile (cheap early catches) and is the
fallback verification path when no TeX engine is available at all.

Checks (per file, main.tex + recursively \\input/\\include'd files):
  encoding          file is valid UTF-8; BOM and non-UTF-8 bytes flagged
  structure         \\documentclass and \\end{document} present in main file
  environment       \\begin{X}/\\end{X} balance and nesting order
  math              unbalanced $ / $$ / \\( \\) / \\[ \\] (comment-aware)
  file_missing      \\input, \\include, \\includegraphics, \\bibliography,
                    \\addbibresource targets exist on disk
  ref_missing       \\ref/\\eqref/\\autoref/\\pageref/\\cref/\\Cref targets have
                    a matching \\label
  label_duplicate   same \\label defined twice
  citation_missing  \\cite keys absent from every reachable .bib file

Usage:
  python latex_preflight.py --project DIR [--main FILE] [--out preflight.json] [--text]

Exit codes: 0 no error-level findings; 1 error-level findings present;
2 main file not found / unreadable.
"""

import argparse
import glob
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

RE_ENV = re.compile(r"\\(begin|end)\s*\{([^}]+)\}")
RE_LABEL = re.compile(r"\\label\s*\{([^}]+)\}")
RE_REF = re.compile(r"\\(?:eqref|autoref|pageref|[cC]?ref|ref)\s*\{([^}]+)\}")
RE_CITE = re.compile(r"\\[a-zA-Z]*cite[a-zA-Z]*\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}")
RE_INPUT = re.compile(r"\\(?:input|include)\s*\{([^}]+)\}")
RE_GRAPHICS = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\s*\{([^}]+)\}")
RE_BIBLIO = re.compile(r"\\bibliography\s*\{([^}]+)\}")
RE_ADDBIB = re.compile(r"\\addbibresource(?:\[[^\]]*\])?\s*\{([^}]+)\}")
RE_BIBENTRY = re.compile(r"@\w+\s*\{\s*([^,\s]+)")
RE_COMMENT = re.compile(r"(?<!\\)%.*$")

GRAPHICS_EXTS = (".pdf", ".png", ".jpg", ".jpeg", ".eps")


def strip_comment(line):
    return RE_COMMENT.sub("", line)


def read_text(path):
    """Return (text, encoding_issue) where issue is None|'bom'|'decode'."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        return None, "decode"
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
        bom = True
    else:
        bom = False
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw.decode("utf-8", errors="replace")
        except Exception:
            return None, "decode"
        return text, "decode"
    return text, ("bom" if bom else None)


def find_main(project):
    cands = []
    for path in glob.glob(os.path.join(project, "**", "*.tex"), recursive=True):
        parts = set(os.path.relpath(path, project).split(os.sep))
        if parts & {".git", "node_modules", "__pycache__"}:
            continue
        text, _ = read_text(path)
        if text and re.search(r"\\documentclass\b", text):
            cands.append(path)
    if not cands:
        return None
    preferred = {"main.tex", "paper.tex", "thesis.tex"}
    for p in cands:
        if os.path.basename(p).lower() in preferred:
            return p
    cands.sort(key=lambda p: (len(os.path.relpath(p, project)), p))
    return cands[0]


class Preflight:
    def __init__(self, project, main):
        self.project = os.path.abspath(project)
        self.main = os.path.abspath(main)
        self.findings = []
        self.visited = set()
        self.labels = {}          # key -> (file, line)
        self.refs = []            # (key, file, line)
        self.cites = []           # (key, file, line)
        self.bib_keys = set()
        self.bib_files = set()
        self.graphicspath = []

    def add(self, category, severity, file, line, message, hint):
        self.findings.append({
            "category": category, "severity": severity,
            "file": os.path.relpath(file, self.project) if file else None,
            "line": line, "message": message, "suggested_fix": hint,
        })

    def resolve(self, target, base_dir, exts=(".tex",)):
        t = target.strip()
        cands = [t] if os.path.splitext(t)[1] else [t + e for e in exts]
        for c in cands:
            p = os.path.normpath(os.path.join(base_dir, c))
            if os.path.isfile(p):
                return p
        return None

    def resolve_graphics(self, target, base_dir):
        t = target.strip()
        dirs = [base_dir] + [os.path.normpath(os.path.join(
            os.path.dirname(self.main), g)) for g in self.graphicspath]
        for d in dirs:
            p = os.path.join(d, t)
            if os.path.splitext(t)[1]:
                if os.path.isfile(p):
                    return p
            else:
                for e in GRAPHICS_EXTS:
                    if os.path.isfile(p + e):
                        return p + e
        return None

    def scan(self, path):
        if path in self.visited:
            return
        self.visited.add(path)
        text, enc = read_text(path)
        if text is None:
            self.add("encoding", "error", path, None,
                     "文件无法读取或非 UTF-8 编码",
                     "统一转换为 UTF-8 无 BOM；旧 GBK 文件用编辑器另存为 UTF-8")
            return
        if enc == "bom":
            self.add("encoding", "warning", path, 1,
                     "文件含 UTF-8 BOM，部分老旧模板/工具链会报错",
                     "另存为 UTF-8 无 BOM")
        elif enc == "decode":
            self.add("encoding", "error", path, None,
                     "文件含非 UTF-8 字节序列",
                     "统一转换为 UTF-8 编码")

        base = os.path.dirname(path)
        lines = text.splitlines()
        is_main = (path == self.main)

        if is_main:
            if not re.search(r"\\documentclass\b", text):
                self.add("structure", "error", path, None,
                         "主文件缺少 \\documentclass", "补全文档类声明")
            if not re.search(r"\\end\s*\{document\}", text):
                self.add("structure", "error", path, None,
                         "主文件缺少 \\end{document}", "补全文末环境结束")
            m = re.search(r"\\graphicspath\s*\{((?:\{[^}]*\})+)\}", text)
            if m:
                self.graphicspath = re.findall(r"\{([^}]*)\}", m.group(1))

        # --- environments (stack over begin/end tokens) ---
        stack = []
        for ln, line in enumerate(lines, 1):
            code = strip_comment(line)
            for m in RE_ENV.finditer(code):
                kind, name = m.group(1), m.group(2)
                if name in ("document",) and not is_main:
                    pass
                if kind == "begin":
                    stack.append((name, ln))
                else:
                    if not stack:
                        self.add("environment", "error", path, ln,
                                 "\\end{%s} 没有匹配的 \\begin" % name,
                                 "删除多余 \\end 或补对应 \\begin")
                    elif stack[-1][0] == name:
                        stack.pop()
                    else:
                        open_name, open_ln = stack[-1]
                        self.add("environment", "error", path, ln,
                                 "\\begin{%s}（第 %d 行）被 \\end{%s} 错误闭合"
                                 % (open_name, open_ln, name),
                                 "核对环境嵌套顺序；常见为漏写 \\end{%s}" % open_name)
                        # try to resync: pop if the name exists deeper
                        names = [s[0] for s in stack]
                        if name in names:
                            while stack and stack[-1][0] != name:
                                stack.pop()
                            if stack:
                                stack.pop()
        for name, ln in stack:
            if name == "document" and not is_main:
                continue
            self.add("environment", "error", path, ln,
                     "\\begin{%s} 未闭合" % name,
                     "在对应位置补 \\end{%s}" % name)

        # --- math delimiters (rough, comment-aware, per file) ---
        code_all = "\n".join(strip_comment(l) for l in lines)
        code_all = code_all.replace("\\$", "")
        n_dollar = code_all.count("$")
        n_ddollar = code_all.count("$$")
        if (n_dollar - 2 * n_ddollar) % 2 != 0 or n_ddollar % 2 != 0:
            self.add("math", "error", path, None,
                     "行内/显示数学定界符数量不配对（$ 或 $$ 为奇数）",
                     "逐个公式检查 $...$ 闭合；正文货币符号用 \\$")
        for open_t, close_t in ((r"\(", r"\)"), (r"\[", r"\]")):
            o = code_all.count(open_t)
            c = code_all.count(close_t)
            if o != c:
                self.add("math", "error", path, None,
                         "%s 与 %s 数量不配对（%d vs %d）" % (open_t, close_t, o, c),
                         "检查数学环境定界符配对")

        # --- labels / refs / cites ---
        for ln, line in enumerate(lines, 1):
            code = strip_comment(line)
            for m in RE_LABEL.finditer(code):
                key = m.group(1).strip()
                if key in self.labels:
                    self.add("label_duplicate", "error", path, ln,
                             "\\label{%s} 重复定义（首次见 %s:%s）"
                             % (key, self.labels[key][0], self.labels[key][1]),
                             "重命名其中一个标签并同步修改引用")
                else:
                    self.labels[key] = (os.path.relpath(path, self.project), ln)
            for m in RE_REF.finditer(code):
                self.refs.append((m.group(1).strip(), path, ln))
            for m in RE_CITE.finditer(code):
                for key in m.group(1).split(","):
                    key = key.strip()
                    if key:
                        self.cites.append((key, path, ln))

        # --- inputs / graphics / bib files ---
        for ln, line in enumerate(lines, 1):
            code = strip_comment(line)
            for m in RE_INPUT.finditer(code):
                tgt = self.resolve(m.group(1), base)
                if tgt:
                    self.scan(tgt)
                else:
                    self.add("file_missing", "error", path, ln,
                             "\\input/\\include 目标不存在: %s" % m.group(1),
                             "核对相对路径与文件名大小写（评测环境为 Linux，区分大小写）")
            for m in RE_GRAPHICS.finditer(code):
                if not self.resolve_graphics(m.group(1), base):
                    self.add("file_missing", "error", path, ln,
                             "图片文件不存在: %s" % m.group(1),
                             "核对图片路径/扩展名；确认 \\graphicspath 设置")
            for m in RE_BIBLIO.finditer(code):
                for name in m.group(1).split(","):
                    p = self.resolve(name.strip(), base, exts=(".bib",))
                    if p:
                        self.bib_files.add(p)
                    else:
                        self.add("file_missing", "error", path, ln,
                                 ".bib 数据库不存在: %s" % name.strip(),
                                 "核对 \\bibliography 路径；确认 .bib 随工程提供")
            for m in RE_ADDBIB.finditer(code):
                p = self.resolve(m.group(1), base, exts=(".bib",))
                if p:
                    self.bib_files.add(p)
                else:
                    self.add("file_missing", "error", path, ln,
                             ".bib 数据库不存在: %s" % m.group(1),
                             "核对 \\addbibresource 路径")

    def finish(self):
        # bib keys
        for bf in sorted(self.bib_files):
            text, _ = read_text(bf)
            if text:
                self.bib_keys.update(k.strip() for k in RE_BIBENTRY.findall(text))
        if self.bib_files or self.cites:
            for key, path, ln in self.cites:
                if key not in self.bib_keys:
                    self.add("citation_missing", "error", path, ln,
                             "\\cite 键 '%s' 在所有 .bib 中无对应条目" % key,
                             "核对键名拼写或向 .bib 补条目；补后需完整 bib 轮次")
        for key, path, ln in self.refs:
            if key not in self.labels:
                self.add("ref_missing", "error", path, ln,
                         "\\ref 目标 '%s' 无对应 \\label" % key,
                         "核对键名拼写或为被引对象补 \\label；注意区分章节/公式/图表标签")

    def run(self):
        self.scan(self.main)
        self.finish()
        order = {"error": 0, "warning": 1, "info": 2}
        self.findings.sort(key=lambda f: (order.get(f["severity"], 9),
                                          f["file"] or "", f["line"] or 0))
        sev = {}
        for f in self.findings:
            sev[f["severity"]] = sev.get(f["severity"], 0) + 1
        return {
            "tool": "latex_preflight/1",
            "project": self.project,
            "main_tex": self.main,
            "files_checked": len(self.visited),
            "bib_files": sorted(os.path.relpath(b, self.project)
                                for b in self.bib_files),
            "labels": len(self.labels), "refs": len(self.refs),
            "cite_keys_used": len({k for k, _, _ in self.cites}),
            "bib_entries": len(self.bib_keys),
            "summary": sev,
            "findings": self.findings,
        }


def main():
    ap = argparse.ArgumentParser(description="static LaTeX source preflight")
    ap.add_argument("--project", default=".")
    ap.add_argument("--main", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--text", action="store_true")
    args = ap.parse_args()

    main_tex = args.main or find_main(args.project)
    if not main_tex:
        print(json.dumps({"error": "no main .tex found in %s" % args.project},
                         ensure_ascii=False))
        sys.exit(2)
    result = Preflight(args.project, main_tex).run()
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
    if args.text or not args.out:
        print("main=%s files=%d labels=%d refs=%d cites=%d bib_entries=%d"
              % (os.path.basename(result["main_tex"]), result["files_checked"],
                 result["labels"], result["refs"], result["cite_keys_used"],
                 result["bib_entries"]))
        print("findings:", result["summary"])
        for f in result["findings"][:15]:
            print("[%s|%s] %s:%s -- %s" % (f["severity"], f["category"],
                                           f["file"], f["line"] or "?",
                                           f["message"][:100]))
    sys.exit(1 if result["summary"].get("error") else 0)


if __name__ == "__main__":
    main()
