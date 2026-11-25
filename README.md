# latex-write-build：LaTeX 写作与编译 Skill 使用说明

## 概述

面向 Agent 的 LaTeX 学术写作与编译排错 Skill。聚焦一个明确问题：**在固定科研材料
与模板约束下，交付能编译通过、内容正确、可复核、可复现的 LaTeX 产物**。核心方法：

1. **构建自动化**：主文件与引擎自动探测，nonstopmode + file-line-error 多轮编译，
   bibtex/biber 轮次自动插入，aux 哈希收敛判定（脚本，非模型数轮次）。
2. **错误分诊**：把日志错误归类为 15 个稳定类别，定位到文件、行号与根因，按
   P0→P3 输出修复队列，破除“停在第一条错误/被级联错误淹没”的常态失败。
3. **诚实交付闭环**：事实-来源映射、逐条修改记录、不确定性标注、output_contract
   字段完整性校验，部分结果明确标注边界。

## 环境与依赖

| 依赖 | 版本 | 获取 | 用途 |
|-|-|-|-|
| Python 3 | ≥ 3.8，仅标准库 | 镜像预装 / python.org | 运行三个脚本 |
| TeX 发行版 | TeX Live 2023+ 或 MiKTeX | 平台 latex-compiler 工具，或 texlive/texlive 镜像 | pdflatex/xelatex/lualatex、bibtex/biber、kpsewhich |
| PDF 文本/渲染工具 | 平台提供 | pdf-text-tool / pdf-render-tool | 材料解析与产物目检 |

无 pip 依赖、无网络依赖、无作者个人文件依赖；脚本路径全部相对于 SKILL.md 所在目录。

## 文件结构

```
SKILL.md                        Skill 本体（触发条件、流程、异常处置）
README.md                       本说明
scripts/latex_preflight.py      无引擎静态预检 → preflight.json
scripts/latex_build.py          多轮编译驱动 → build-report.json
scripts/latex_log_triage.py     日志错误分诊 → triage.json
scripts/result_emit.py          result.json 装配与契约校验
references/error-catalog.md     错误类别-根因-修复策略目录
references/build-recipes.md     引擎/轮次/模板核查清单/复现记录
references/output-contract.md   result.json 字段语义与填写纪律
references/self-check-rubric.md 交付前自查评分表（五张表）
examples/log-triage-demo/       分诊演示（合成日志+预期输出，无需 TeX，示例）
examples/minimal-broken/        最小编译-修复示例（示意输出已标注）
```

## 调用步骤

```bash
export SKILL_DIR=<本 Skill 安装目录>   # 平台评测时为 /skills/weekly-skill
cd /app/work && cp -r /input/<工程材料> proj && cd proj

# 1. 静态预检（秒级，无需 TeX；退出码 0 无 error / 1 有 error / 2 找不到主文件）
python "$SKILL_DIR/scripts/latex_preflight.py" --project . --out ../preflight.json --text

# 2. 基线构建（自动探测主文件与引擎；可 --main/--engine 覆盖）
python "$SKILL_DIR/scripts/latex_build.py" --project . --report ../build-report.json
#    退出码：0 成功；1 有错误；2 找不到主文件；3 环境缺引擎；4 超时

# 3. 错误分诊（有错误时）
python "$SKILL_DIR/scripts/latex_log_triage.py" main.log --out ../triage.json --text

# 4. 按 fix_queue 修复后回到 1；收敛后按 references/self-check-rubric.md 自查
# 5. 装配结果（answers.json 由 agent 汇总，见 references/output-contract.md）
python "$SKILL_DIR/scripts/result_emit.py" --case /input/case.json \
    --answers ../answers.json --out /app/output/result.json
```

输入输出：`latex_preflight.py` 读源码、写 preflight.json（环境配对/缺失文件/
引用键/编码等静态 findings）；`latex_build.py` 读工程目录、写 build-report.json
（状态/轮次/版本/错误计数）；`latex_log_triage.py` 读 .log/.blg、写 triage.json
（分类 findings 与修复队列）；`result_emit.py` 读 case.json + answers.json、写
result.json 并报告缺失契约字段。

## 适用场景与限制

适用：LaTeX 稿件生成/改写/校对、模板迁移、参考文献整理、编译排错与可复现构建；
中英文学术模板（article、ctex 系列、常见期刊会议 .cls）。

限制：① 不处理 Word/InDesign 源（先人工转 .tex）；② 宏包冲突涉及 .cls 私有宏定义
时需要人工判断；③ 缺少 TeX 引擎的环境降级为 latex_preflight.py 静态核查并如实
标注未经真实编译；④ overfull_box 等版式修复给出策略但不保证全自动消除。

## 失败处理与自查

- 任何阶段受阻：先以现有 answers.json 跑 result_emit.py 保存 `status=partial` 的
  result.json，`limits` 写明卡点；继续后重新装配。
- 交付前逐项过 `references/self-check-rubric.md` 五张自查表（编译得通/改得对/
  交得可用/复现得了/事实与边界），未通过项修复或写入 uncertainty（按
  materials_missing / undecidable / run_failed 三分标注）。
- 维护：错误类别表在 references/error-catalog.md，新增类别同步在
  latex_log_triage.py 的 RULES 中追加一行即可。

## 最小示例

- `examples/log-triage-demo/README.md`：无需 TeX 的分诊演示（合成日志 + 预期
  输出，可复跑核对，已标注为示例）；
- `examples/minimal-broken/README.md`：最小编译-修复闭环示例（需 TeX，
  示意输出已标注，非正式案例结果）。

版本：1.1.0（2026-11）：新增 latex_preflight.py 静态预检、log-triage-demo
可复跑示例、self-check-rubric.md 自查评分表；uncertainty 三分标注。
反馈与维护：随参赛提交材料一并维护，仓库地址见 GITHUB_URL.txt。
