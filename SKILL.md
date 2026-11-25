---
name: latex-write-build
description: >-
  LaTeX 学术写作与编译排错闭环。当任务涉及撰写/改写/校对 LaTeX 稿件、模板适配、
  公式表格与参考文献处理、修复编译错误，或要求交付可编译、可复核、可复现的 .tex
  成果与结构化 result.json 时使用。提供无引擎静态预检、主文件与引擎自动探测、
  多轮编译驱动、日志错误分诊（定位到文件、行号与根因）、参考文献轮次与收敛控制、
  事实-来源映射和 output_contract 结果装配脚本。
---

# LaTeX 写作与编译 Skill（latex-write-build）

## 1. 用途与适用条件

本 Skill 面向一个明确问题：**在固定科研材料与模板约束下，交付能编译通过、内容正确、
可复核且可复现的 LaTeX 学术写作产物**，并保留全部来源与修改记录。适用任务包括：

- 依据给定材料生成或改写 LaTeX 稿件、摘要、表格、公式与参考文献；
- 将已有稿件迁入期刊/会议/学位论文模板并保持版式合规；
- 定位并修复编译错误与警告，稳定编译轮次，使构建可被他人复现。

不适用：纯自然语言写作（无 LaTeX 交付物）、与材料无关的自由创作。

## 2. 运行环境与资源

- 脚本仅依赖 Python 3 标准库，位于 `scripts/`；`SKILL_DIR` 指本 SKILL.md 所在目录。
- TeX 引擎（pdflatex/xelatex/lualatex、bibtex/biber、latexmk、kpsewhich）由平台的
  latex-compiler 工具或系统 TeX 发行版提供；PDF 文本/渲染工具用于核对编译产物。
- 平台运行时：输入为 `/input/case.json` 与 `task.md`（及随附材料），在 `/app/work`
  下工作，交付物写入 `/app/output`，其中必须含 `result.json`。
- 预算纪律（64 次请求 / 900 秒）：**先跑脚本、后读日志、按类修复**。每一轮编译修复
  一类最高优先级错误后再整轮重编译，禁止每改一行就编译；修复迭代上限 6 轮，
  第 3 轮仍未收敛时先保存部分结果（见 §7），再继续。

## 3. 总流程

### 阶段 0：读任务与材料（1–2 次请求内完成）

1. 读 `/input/case.json`：记录 `case_id`、`output_contract` 的全部字段名（result.json
   必须逐项覆盖）、体裁/受众/格式约束。
2. 读 `task.md` 与随附材料清单。**实际打开文件阅读**，不凭文件名猜测内容；PDF 用
   平台 PDF 文本工具解析，图片材料必要时用 OCR。
3. 建立事实底稿表：关键数字、术语、论断 → 来源（文件名+页码/行号）。后续写入
   result.json 的 `sources`，**不得新增材料之外的事实**。

### 阶段 1：静态预检与构建基线

```bash
cd /app/work && cp -r /input/<工程材料> proj && cd proj
# 1a. 静态预检（秒级、无需 TeX 引擎）：环境配对、数学定界符、缺失文件、
#     ref/cite 键与 .bib 对应、重复 label、编码问题
python "$SKILL_DIR/scripts/latex_preflight.py" --project . --out /app/work/preflight.json --text
# 1b. 构建基线
python "$SKILL_DIR/scripts/latex_build.py" --project . --report /app/work/build-report.json
```

预检发现的 error 级问题（缺文件、环境不配对、缺 label/bib 条目）就地修复后再编译，
可省去多轮"编译-看日志"往返；预检也是无 TeX 引擎环境下的降级验证路径（见 §6）。
`latex_build.py` 自动完成：主文件探测（找含 `\documentclass` 的根文件）、引擎选择
（ctex/xeCJK/fontspec → xelatex）、多轮编译（nonstopmode + file-line-error）、按需
插入 bibtex/biber 轮次、aux 哈希收敛检测、版本记录。`--engine` 与 `--main` 可显式
覆盖。若返回 `environment_error`（缺引擎/缺类文件），按 §6 异常处置，不要编造编译
结果。

### 阶段 2：错误分诊与修复闭环

```bash
python "$SKILL_DIR/scripts/latex_log_triage.py" proj/<主文件名>.log \
    --out /app/work/triage.json --text
```

分诊脚本把每条错误/警告归类（missing_package、undefined_control_sequence、
math_mode_error、undefined_citation、overfull_box 等，详见
`references/error-catalog.md`），给出文件、行号、根因与修复建议，并按
P0→P3 输出修复队列。修复纪律：

1. 每轮只处理队列中最高优先级的一类问题；`Emergency stop` 是级联结果，修最早的
   真实错误即可消除，不要逐条纠缠。
2. 缺宏包/类文件先用 `kpsewhich 名称` 验证再安装或修正路径；缺字体用平台
   font-discovery 或 `fc-list` 查可用字体，替换必须记入变更记录。
3. 仅剩 undefined_reference/undefined_citation/rerun 类时，先补 bib 轮次与额外
   编译轮次，多轮不消才核对 `\label` 与 `.bib` 键名。
4. 每次修改记录：文件、行号、改前、改后、依据（错误签名或任务要求）→ 写入
   `changes`。修复后回到阶段 1 重跑 `latex_build.py`，直至 `status=success`
   且 `converged=true`。

### 阶段 3：内容正确性核查（改得对）

编译通过后逐项核对，不满足则回到阶段 2：

- **公式**：编号与正文 `\eqref` 一致；符号与材料底稿一致；变量斜体、单位与函数名
  正体；多行公式对齐点正确。
- **表格**：数值与材料逐格一致；三线表用 booktabs；宽表不溢出（溢出按
  error-catalog 的 overfull_box 条目处理，禁止 `\resizebox` 整体缩放掩盖）。
- **引用与参考文献**：`\cite` 键与 .bib 条目一一对应；多轮编译后无 undefined
  citation；样式符合任务要求（GB/T 7714 用 gbt7714 宏包）。
- **模板合规**：`\documentclass` 选项、必填字段（标题、作者、摘要、关键词等）齐全；
  浮动体位置约束合理。核查清单详见 `references/build-recipes.md` §4。
- **版式抽检**：用 PDF 渲染工具把产物首页与关键页渲染为 PNG 目检，确认无乱码、
  无溢出、图表完整。
- **交付前自查**：逐项过 `references/self-check-rubric.md`（编译得通/改得对/交得可用/
  复现得了/事实与边界 五张表），未通过项修复或写入 uncertainty。

### 阶段 4：交付与复现记录

1. 把可编辑源码（.tex、.bib、图片、.cls/.sty 等配套文件）与编译产物 PDF 复制到
   `/app/output`；同时放一份关键页 PNG 预览供人工检查。
2. 在 `/app/work/answers.json` 汇总：output_contract 各字段、`status`、`sources`
   （事实-来源映射）、`changes`（修改记录）、`uncertainty`、`artifacts`、
   `build_report`（引擎与版本、轮次、收敛情况——即复现记录）。`uncertainty`
   条目按题目要求**三分标注**：`kind: materials_missing`（材料缺失）、
   `kind: undecidable`（无法判断）、`kind: run_failed`（运行失败），
   不得混写或省略。
3. 装配结果：

```bash
python "$SKILL_DIR/scripts/result_emit.py" --case /input/case.json \
    --answers /app/work/answers.json --out /app/output/result.json
```

脚本保证 result.json 含 `case_id` 与 output_contract 全部字段；缺字段会置 null
并列入 `missing_contract_fields`，**绝不留空不报**。字段规范见
`references/output-contract.md`。

## 4. 写作纪律（事实与来源）

- 每个数字、术语、图表和关键论断必须能回溯到 `/input` 材料的具体位置；无法回溯的
  内容不写入产物。
- 材料不足、相互冲突或需人工判断处：在产物中用 `% TODO(确认): ...` 标注，并在
  `uncertainty` 中逐条说明，不得静默编造。
- 改写保持原文意图与证据强度：材料中的初步结论不得写成确证结论。

## 5. 最小调用示例

两组示例（输入、调用、示意输出均已标注为示例，非正式案例结果）：

- `examples/log-triage-demo/`：**无需 TeX 环境**，合成日志 + 预期分诊输出，
  可直接复跑核对分诊能力；
- `examples/minimal-broken/`：含两类典型错误的最小工程，演示完整编译-修复闭环
  （需 TeX 环境）。

一分钟验证 Skill 可用：

```bash
python scripts/latex_log_triage.py examples/log-triage-demo/demo.log \
    --blg examples/log-triage-demo/demo.blg --text
python scripts/latex_preflight.py --project examples/minimal-broken --text
```

## 6. 异常处置

| 情形 | 识别 | 处置 |
|-|-|-|
| 无 TeX 引擎 | build 报告 `environment_error` | 改调平台 latex-compiler 工具；仍不可用时运行 `latex_preflight.py` 完成静态核查，交付源码+preflight 报告并注明未经真实编译，`status=partial`、`kind: run_failed` 写明缺失软件状态，禁止伪造编译成功 |
| 缺 .cls/.sty | triage `missing_class`/`missing_package` | kpsewhich 验证→包管理器安装或补随工程文件；无法获得时在 uncertainty 说明 |
| 缺字体 | triage `font_missing` | fc-list/font-discovery 找已安装替代字体，替换记入 changes |
| 报错级联 | 大量错误+`emergency_stop` | 只修 fix_queue 首个 P0/P1，重编译后重新分诊 |
| 主文件不明 | `no_main_tex` 或选错 | 用 `--main` 显式指定含 `\documentclass` 的根文件 |
| 单轮超时 | build `timeout` | 检查死循环（如未闭合环境）；提高 `--timeout`；记录为异常 |
| 写权限不足 | 复制/编译报权限错 | 工作目录换到 /app/work 可写区，产物写 /app/output |
| 材料缺失或冲突 | 阶段 0 底稿表出现空洞 | uncertainty 标注+产物内 TODO 标注，不编造 |

## 7. 部分结果与诚实状态

任何阶段受阻时：立即用现有 answers.json 跑 `result_emit.py` 保存
`status=partial` 的 result.json，`limits` 写明卡点与已完成范围；继续修复后重新装配。
文字自述不替代运行证据：build-report.json、triage.json 与日志一并保留在 /app/work，
可随交付说明引用。
