#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""latex_log_triage.py -- classify LaTeX log errors to file, line and root cause.

Reads a .log produced with -file-line-error (classic logs also supported)
and, optionally, a BibTeX/Biber .blg file. Emits a JSON list of findings,
each carrying:
  category     stable machine category (see references/error-catalog.md)
  priority     P0 build-stopping, P1 must-fix, P2 convergence, P3 cosmetic
  file / line  best-effort source location
  signature    the exact log evidence (quote this in change records)
  root_cause   short hypothesis
  suggested_fix
plus a summary ordered so the agent fixes blockers first instead of
stopping at the first error line.

Usage:
  python latex_log_triage.py LOG [--blg FILE] [--out findings.json] [--text]

Exit code: 0 always (triage itself succeeded); 2 if the log is unreadable.
"""

import argparse
import json
import os
import re
import sys

try:  # keep Chinese readable on Windows consoles
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ---------------------------------------------------------------------------
# classification rules: (category, priority, pattern, root_cause, suggested_fix)
# matched against the error/warning message text.
# ---------------------------------------------------------------------------
RULES = [
    ("missing_class", "P0",
     re.compile(r"(?:No file|File `)([^\s']+\.cls)'? (?:not found)?", re.I),
     "模板类文件缺失或 \\documentclass 名称拼写错误",
     "确认模板 .cls 随工程提供且路径正确；用 kpsewhich X.cls 验证；核对 \\documentclass 拼写"),
    ("missing_package", "P0",
     re.compile(r"File `([^']+\.sty)' not found", re.I),
     "宏包未安装或名称拼写错误",
     "kpsewhich X.sty 检查；用发行版包管理器安装；核对 \\usepackage 拼写；不要引入未经验证的替代宏包"),
    ("missing_input_file", "P0",
     re.compile(r"(?:No file|cannot (?:open|find) input file) [`']?([^'\s]+\.(?:tex|inc|def|bib|bst|png|jpg|jpeg|pdf|eps))", re.I),
     "\\input/\\include/图片/参考文献文件缺失或路径错误",
     "核对相对路径与文件名大小写（Linux 区分大小写）；确认资源已随工程提供"),
    ("undefined_control_sequence", "P1",
     re.compile(r"Undefined control sequence", re.I),
     "命令拼写错误、宏包未加载或命令定义缺失",
     "查看 l.N 上下文中的命令名：拼写错误直接改正；属于某宏包的命令则在导言区补 \\usepackage；自定义命令核对 \\newcommand 定义位置"),
    ("math_mode_error", "P1",
     re.compile(r"Missing \$ inserted|Display math should end|Double subscript|Double superscript|Misplaced alignment tab|Extra alignment tab|Missing \\cr inserted|Bad math environment delimiter", re.I),
     "数学模式使用错误（$ 缺失、上下标重复、对齐符越界）",
     "定位 l.N：补全 $...$ / 公式环境；上下标分组加花括号；检查 tabular/array 列数与 & 数量一致"),
    ("environment_error", "P1",
     re.compile(r"\\begin\{([^}]+)\} (?:on input line \d+ )?ended by \\end\{([^}]+)\}|Environment ([^ ]+) undefined|Missing \\endgroup", re.I),
     "环境不配对或未定义",
     "核对 \\begin/\\end 名称一致；未定义环境补相应宏包（如 amsthm 的 proof）"),
    ("package_option_clash", "P1",
     re.compile(r"Option clash for package ([^ .]+)", re.I),
     "同一宏包被不同选项重复加载",
     "合并选项到首次加载处；注意模板 .cls 内部已加载的宏包（如 hyperref 应最后加载）"),
    ("font_missing", "P1",
     re.compile(r"fontspec error|Font .* (?:not found|does not contain)|Missing character: There is no|Cannot find font|kpathsea:.*mktex", re.I),
     "字体缺失或当前引擎不支持该字体调用",
     "XeLaTeX/LuaLaTeX 用 fc-list / font-discovery 查可用字体并改名；勿删除字体声明后静默换字体，需在变更记录中注明"),
    ("emergency_stop", "P0",
     re.compile(r"Emergency stop|Fatal error occurred|no output PDF file produced", re.I),
     "编译被前序错误终止（级联）",
     "按本报告的 P0/P1 顺序先修复最早的真实错误，Emergency stop 通常随之消失"),
    ("undefined_reference", "P2",
     re.compile(r"Reference [`']([^']+)' on page \d+ undefined", re.I),
     "交叉引用未解析：轮次不足或 \\label 缺失/拼写错误",
     "先再跑一轮编译；多轮后仍存在则核对 \\label 与 \\ref/\\eqref/\\autoref 的键名一致"),
    ("undefined_citation", "P2",
     re.compile(r"Citation [`']([^']+)' on page \d+ undefined|Empty `thebibliography'|I found no \\citation", re.I),
     "文献引用未解析：缺 bibtex/biber 轮次或 .bib 条目缺失",
     "运行 latex_build.py（自动插入 bib 轮次）；仍存在则核对 \\cite 键与 .bib 条目，并检查 .blg 中的 BibTeX 错误"),
    ("rerun_needed", "P2",
     re.compile(r"Rerun to get cross-references right|Please rerun|Label\(s\) may have changed", re.I),
     "交叉引用/目录尚未收敛",
     "再运行一轮编译；latex_build.py 的 aux 哈希收敛检测会自动处理"),
    ("overfull_box", "P3",
     re.compile(r"(Overfull|Underfull) \\[hv]box \(([\d.]+)pt too (wide|high|large)", re.I),
     "版式溢出/欠满（不影响编译通过）",
     "表格溢出优先调列宽（p{} 列、tabulary）或缩字号局部处理，禁止用 \\resizebox/\\scalebox 整体掩盖；行溢出检查长 URL/数学式断行"),
    ("bibtex_error", "P1",
     re.compile(r"^(?:Error|error)|couldn't open|I found no|I was unable|Illegal,|You're missing|---line \d+ of file", re.I),  # .blg lines
     "BibTeX/Biber 数据库错误（.bib 缺失、重复条目、非法字符）",
     "打开 .blg 对应行定位 .bib 问题：文件缺失则核对 \\bibliography 路径；重复键合并条目；修后重跑含 bib 轮次的构建"),
    ("bibtex_warning", "P2",
     re.compile(r"^Warning--", re.I),  # only used for .blg lines
     "BibTeX 条目字段缺失或格式问题",
     "按 .blg 提示补字段（如 year、pages）；核对条目键与正文 \\cite 一致"),
    ("generic_warning", "P3",
     re.compile(r"(LaTeX|Package|Class) .*Warning", re.I),
     "一般警告",
     "评估是否与任务要求的版式/引用相关；无关可在交付说明中列出"),
]

FILELINE_ERR = re.compile(r"^(?P<file>[^\s()][^:()]*\.tex):(?P<line>\d+):\s*(?P<msg>.*)$")
CLASSIC_ERR = re.compile(r"^!\s*(?P<msg>.*)$")
LINE_MARKER = re.compile(r"^l\.(?P<line>\d+)\s*(?P<context>.*)$")
UNDEF_CS_CONTEXT = re.compile(r"\\[A-Za-z@]+")


class FileTracker:
    """Track TeX's current input file via the parenthesis convention.

    Approximation of latexmk's algorithm: '(' followed by a path token pushes
    that file; ')' pops. Line wrapping at column 79 can split tokens, so we
    glue a wrapped path back together when it contains no whitespace break
    marker. Good enough for locating the offending file in practice.
    """

    PATH_CHARS = re.compile(r"^\(?([^\s()]+)$")

    def __init__(self):
        self.stack = []
        self._pending = ""

    def feed(self, line):
        i = 0
        while i < len(line):
            ch = line[i]
            if ch == "(":
                j = i + 1
                token = ""
                while j < len(line) and line[j] not in " ()\t":
                    token += line[j]
                    j += 1
                # wrapped path: token continues on next line(s)
                if j >= len(line) and token and not token.endswith((".tex", ".sty", ".cls", ".def", ".cfg", ".aux", ".fd", ".clo", ".bib", ".bst")):
                    self._pending = token
                else:
                    token = self._pending + token
                    self._pending = ""
                    if "/" in token or "\\" in token or "." in token:
                        self.stack.append(token)
                i = j
            elif ch == ")":
                if self.stack:
                    self.stack.pop()
                i += 1
            else:
                i += 1

    def current(self):
        return self.stack[-1] if self.stack else None


def classify(msg):
    for category, prio, pat, cause, fix in RULES:
        if category in ("bibtex_error", "bibtex_warning"):
            continue
        if pat.search(msg):
            return category, prio, cause, fix
    return None


def triage_log(log_path):
    findings = []
    tracker = FileTracker()
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return None

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        tracker.feed(line)

        m = FILELINE_ERR.match(line)
        if m:
            msg = m.group("msg")
            hit = classify(msg)
            category, prio, cause, fix = hit or ("other_error", "P1",
                                                 "未归类的编译错误", "阅读 l.N 上下文与 error-catalog 对照定位")
            findings.append({
                "category": category, "priority": prio,
                "file": m.group("file"), "line": int(m.group("line")),
                "signature": line.strip()[:300],
                "message": msg.strip()[:300],
                "root_cause": cause, "suggested_fix": fix,
            })
            i += 1
            continue

        m = CLASSIC_ERR.match(line)
        if m:
            msg = m.group("msg")
            # gather context: following lines; look for l.NN. Tolerate blank
            # lines only before the first content line (some engines emit one
            # right after the error text); a blank after content ends the block.
            lineno, context = None, ""
            j = i + 1
            seen_content = False
            while j < n and j - i < 14:
                if lines[j].strip() == "":
                    if seen_content:
                        break
                    j += 1
                    continue
                seen_content = True
                tracker.feed(lines[j])
                lm = LINE_MARKER.match(lines[j])
                if lm:
                    lineno = int(lm.group("line"))
                    context = lm.group("context").strip()
                    # the offending command may continue on the next line
                    if j + 1 < n and lines[j + 1].strip():
                        context += " " + lines[j + 1].strip()
                    break
                j += 1
            hit = classify(msg)
            if hit:
                category, prio, cause, fix = hit
                if category == "undefined_control_sequence" and context:
                    cmd = UNDEF_CS_CONTEXT.search(context)
                    if cmd:
                        fix = ("出错命令为 %s；" % cmd.group(0)) + fix
                findings.append({
                    "category": category, "priority": prio,
                    "file": tracker.current(), "line": lineno,
                    "signature": line.strip()[:300],
                    "message": msg.strip()[:300],
                    "context": context[:300],
                    "root_cause": cause, "suggested_fix": fix,
                })
            i = j
            continue

        # warnings
        wm = re.search(r"(LaTeX|Package|Class) ([\w@]* ?)Warning: (.*)", line)
        if wm:
            msg = wm.group(3)
            hit = classify(msg)
            if hit:
                category, prio, cause, fix = hit
                lm = re.search(r"on input line (\d+)", line)
                findings.append({
                    "category": category, "priority": prio,
                    "file": tracker.current(),
                    "line": int(lm.group(1)) if lm else None,
                    "signature": line.strip()[:300],
                    "message": msg.strip()[:300],
                    "root_cause": cause, "suggested_fix": fix,
                })
        elif line.startswith("Overfull \\") or line.startswith("Underfull \\"):
            hit = classify(line)
            if hit:
                category, prio, cause, fix = hit
                lm = re.search(r"(?:at lines? |detected at line )(\d+)", line)
                findings.append({
                    "category": category, "priority": prio,
                    "file": tracker.current(),
                    "line": int(lm.group(1)) if lm else None,
                    "signature": line.strip()[:300],
                    "message": line.strip()[:300],
                    "root_cause": cause, "suggested_fix": fix,
                })
        i += 1
    return findings


def triage_blg(blg_path):
    findings = []
    try:
        with open(blg_path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return findings
    for line in lines:
        for category, prio, pat, cause, fix in RULES:
            if category not in ("bibtex_error", "bibtex_warning"):
                continue
            if pat.search(line):
                findings.append({
                    "category": category, "priority": prio,
                    "file": os.path.basename(blg_path), "line": None,
                    "signature": line.strip()[:300], "message": line.strip()[:300],
                    "root_cause": cause, "suggested_fix": fix,
                })
                break
    return findings


def summarize(findings):
    order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    by_cat = {}
    for f in findings:
        by_cat[f["category"]] = by_cat.get(f["category"], 0) + 1
    queue = sorted(findings, key=lambda f: (order.get(f["priority"], 9),
                                            f["file"] or "",
                                            f["line"] or 0))
    return {
        "total_findings": len(findings),
        "by_category": dict(sorted(by_cat.items(), key=lambda kv: -kv[1])),
        "by_priority": {p: sum(1 for f in findings if f["priority"] == p)
                        for p in ("P0", "P1", "P2", "P3")},
        "fix_queue": queue,
        "advice": _advice(findings),
    }


def _advice(findings):
    cats = {f["category"] for f in findings}
    tips = []
    if "emergency_stop" in cats:
        tips.append("存在 Emergency stop：按 fix_queue 从第一个 P0/P1 修起，勿在级联错误上逐条纠缠。")
    if "missing_package" in cats or "missing_class" in cats:
        tips.append("存在缺失文件：先用 kpsewhich 验证，再决定安装宏包或核对路径；修复后整轮重编译。")
    if cats & {"undefined_reference", "undefined_citation", "rerun_needed"} \
            and not cats & {"missing_class", "missing_package", "emergency_stop"}:
        tips.append("仅剩引用类问题时，先补 bibtex/biber 与额外编译轮次，再判断是否真实缺 label/bib 条目。")
    if not findings:
        tips.append("日志中未发现错误或需处理的警告。")
    return tips


def main():
    ap = argparse.ArgumentParser(description="classify LaTeX log errors")
    ap.add_argument("log", help="path to the .log file")
    ap.add_argument("--blg", default=None, help="optional .blg file")
    ap.add_argument("--out", default=None, help="write JSON findings here")
    ap.add_argument("--text", action="store_true", help="print human summary")
    args = ap.parse_args()

    findings = triage_log(args.log)
    if findings is None:
        print(json.dumps({"error": "log unreadable: %s" % args.log},
                         ensure_ascii=False))
        sys.exit(2)
    if args.blg:
        findings += triage_blg(args.blg)
    elif os.path.isfile(re.sub(r"\.log$", ".blg", args.log)):
        findings += triage_blg(re.sub(r"\.log$", ".blg", args.log))

    result = {"log": os.path.abspath(args.log), "summary": summarize(findings),
              "findings": findings}
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
    if args.text or not args.out:
        s = result["summary"]
        print("findings=%d by_priority=%s" % (s["total_findings"],
                                              s["by_priority"]))
        for tip in s["advice"]:
            print("advice: " + tip)
        for f in s["fix_queue"][:12]:
            loc = "%s:%s" % (f["file"] or "?", f["line"] if f["line"] else "?")
            print("[%s|%s] %s -- %s" % (f["priority"], f["category"], loc,
                                        f["message"][:90]))
    sys.exit(0)


if __name__ == "__main__":
    main()
