# LaTeX 编译错误目录（错误分诊规则说明）

`scripts/latex_log_triage.py` 按下表把日志证据映射为类别、优先级、根因与修复策略。
优先级：P0 阻断编译；P1 必须修复；P2 与轮次/引用收敛相关；P3 版式类，不阻断。

## P0：阻断编译

| 类别 | 日志签名 | 根因 | 修复策略 |
|-|-|-|-|
| missing_class | ``File `xxx.cls' not found`` / `No file xxx.cls` | 模板类文件缺失或 `\documentclass` 名称拼写错误 | 确认 .cls 随工程提供且与主文件同目录（或在 TEXMF 路径内）；`kpsewhich xxx.cls` 验证；核对大小写（Linux 敏感） |
| missing_package | ``File `xxx.sty' not found`` | 宏包未安装或拼写错误 | `kpsewhich xxx.sty`；TeX Live 用 `tlmgr install`，MiKTeX 自动安装；核对 `\usepackage` 拼写；不要随意换替代宏包，确需替换记 changes |
| missing_input_file | `No file xxx.tex` / `cannot open input file` | `\input/\include/\includegraphics` 路径或文件名错误 | 相对路径以主文件所在目录为基准；核对大小写与扩展名；确认资源已随工程复制 |
| emergency_stop | `! Emergency stop` / `Fatal error occurred` | 前序错误导致 TeX 终止（级联表象） | 修 fix_queue 中最早的真实 P0/P1 后整轮重编译；不要按日志顺序逐条处理级联错误 |

## P1：必须修复

| 类别 | 日志签名 | 根因 | 修复策略 |
|-|-|-|-|
| undefined_control_sequence | `! Undefined control sequence.` + `l.N \某命令` | 命令拼写错误、宏包未加载、自定义命令定义缺失或顺序错误 | 看 l.N 上下文的命令名：拼写错误直接改；属于宏包的命令在导言区补 `\usepackage`（如 `\si`→siunitx、`\toprule`→booktabs）；自定义命令核对 `\newcommand` 在使用之前 |
| math_mode_error | `Missing $ inserted` / `Double subscript` / `Misplaced alignment tab character &` / `Bad math environment delimiter` | 数学模式误用 | 正文中的 `_^` 等需进 `$...$`；双上下标分组 `x^{a}_{b}`；tabular/array 的 `&` 数与列说明一致；`\begin{equation}` 内不能再有 `$` |
| environment_error | `\begin{X} ended by \end{Y}` / `Environment X undefined` | 环境不配对或未定义 | 逐层核对 `\begin/\end` 名称；未定义环境补宏包（proof→amsthm，algorithm→algorithm/algorithmicx） |
| package_option_clash | `Option clash for package xxx` | 同一宏包以不同选项重复加载（常因 .cls 内部已加载） | 选项合并到首次加载；hyperref 原则最后加载（例外：cleveref 在其后） |
| font_missing | `fontspec error: font-not-found` / `Missing character: There is no X in font` / `Cannot find font` | 引擎找不到声明的字体 | XeLaTeX/LuaLaTeX 用 `fc-list : family` 或平台 font-discovery 查已安装字体；改用可用字体并记 changes；Missing character 多为字体缺该字形（常见：中文字体缺数学符号） |
| bibtex_error | .blg 中 `Error` 行：如 `I couldn't open database file`、重复条目 | .bib 文件缺失/损坏/重复键 | 按 .blg 行定位 .bib；重复键合并条目；修后重跑含 bib 轮次的构建 |

## P2：轮次与引用收敛

| 类别 | 日志签名 | 根因 | 修复策略 |
|-|-|-|-|
| undefined_reference | `Reference 'xxx' on page N undefined` | 轮次不足，或 `\label` 缺失/键名拼写不一致 | 先加跑一轮；多轮仍在则全文搜 `\label{xxx}` 核对；章节号变动后必须两轮 |
| undefined_citation | `Citation 'xxx' undefined` | 未跑 bibtex/biber，或 .bib 无该键 | latex_build.py 会自动插入 bib 轮次（.bcf→biber，否则 bibtex）；仍在则核对 `\cite` 键与 .bib，并查 .blg |
| rerun_needed | `Rerun to get cross-references right` / `Label(s) may have changed` | 交叉引用未收敛 | 再跑一轮；latex_build.py 以 aux 哈希判断收敛，无需人工数轮次 |
| bibtex_warning | .blg 中 `Warning--` 行：如 `empty year in xxx` | 条目字段缺失 | 按提示补字段；GB/T 7714 样式对页码、出版年字段敏感 |

## P3：版式类（不阻断编译，但影响“改得对”）

| 类别 | 日志签名 | 根因 | 修复策略 |
|-|-|-|-|
| overfull_box | `Overfull \hbox (Npt too wide)` | 行/表超出版心 | 表格：改 `p{}` 列宽、`tabularx`/`tabulary`、局部 `\small`；禁止 `\resizebox` 整体缩放掩盖。行内：长 URL 用 `\url` 并加载 `xurl`；长公式改多行 |
| generic_warning | 其他 `LaTeX/Package Warning` | 杂项 | 评估与任务相关性；无关项在交付说明列出，不逐一消除 |

## 级联处理通则

1. TeX 报错具有强级联性：一个 `Missing $ inserted` 可衍生数十条后续错误。
   永远先修 fix_queue 中**文件位置最早**的 P0/P1。
2. 每修一类错误即整轮重编译并重新分诊，不要在旧日志上推断新状态。
3. 修不动的错误：保留现场（日志、triage.json），在 uncertainty 中说明已尝试的策略。
