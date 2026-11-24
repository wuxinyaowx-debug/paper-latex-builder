# 构建配方：引擎、轮次、模板适配与可复现记录

## 1. 引擎选择规则（latex_build.py 已自动执行，此处为判据）

| 源码证据 | 引擎 |
|-|-|
| `\documentclass{ctexart/ctexrep/ctexbook}`、`\usepackage{ctex}`、`\usepackage{xeCJK}`、`\usepackage{fontspec}` | xelatex |
| `\usepackage{luacode}` | lualatex |
| 其他（含 `\usepackage{CJKutf8}` 的旧式中文） | pdflatex |

学位论文/中文期刊模板几乎都要求 xelatex。任务指定引擎时用 `--engine` 显式覆盖，
并在复现记录中写明。

## 2. 参考文献轮次

- 存在 `主文件名.bcf` → biber；存在 `\citation` 的 .aux 且用 `\bibliography` → bibtex。
- 标准收敛序列：引擎 → bibtex/biber → 引擎 → 引擎。latex_build.py 在首轮后自动
  插入一次 bib 轮次，并以 aux 类文件哈希 + 日志 Rerun 提示判断收敛（最多
  `--max-passes` 轮，默认 4）。
- GB/T 7714 参考文献：`\usepackage[authoryear|numbers]{gbt7714}` + `\bibliographystyle{gbt7714-numerical}`（或按模板要求）。

## 3. 可复现构建记录（写入 result.json 的 build_report）

他人复现所需的最小信息，latex_build.py 已全部采集：

```json
{
  "engine": "xelatex",
  "engine_version": "XeTeX 3.141592653-2.6-0.999996 (TeX Live 2024)",
  "documentclass": "ctexart",
  "passes": 3, "bib_tool": "bibtex", "converged": true,
  "cmd": "xelatex -interaction=nonstopmode -file-line-error -synctex=1 main.tex"
}
```

交付说明中补一句发行版与获取方式（如“TeX Live 2024，镜像内 latex-compiler 工具”）。
模板自带 .cls/.sty 必须随源码一并交付，不依赖本机私藏文件。

## 4. 模板适配核查清单（改得对）

1. **必填项**：`\documentclass` 选项、`\title`、`\author`、`\date`、摘要、关键词、
   `\maketitle`——对照模板示例逐项打勾。
2. **宏包加载顺序**：amsmath 早于 amsthm；hyperref 最后（cleveref 例外在其后）；
   模板 .cls 已加载的宏包不重复带冲突选项加载（防 option clash）。
3. **公式**：编号连续且与正文 `\eqref` 一致；物理量斜体、单位与函数名（sin、log、
   max）正体；多行公式用 `align`/`split` 对齐关系号；不在 equation 内嵌 `$`。
4. **表格**：学术三线表用 booktabs（`\toprule/\midrule/\bottomrule`，无竖线）；
   数值与材料逐格一致（含有效数字与单位）；宽表用 `tabularx`/`p{}` 列或 `longtable`
   跨页；`Overfull \hbox` 必须消除，禁用 `\resizebox` 掩盖。
5. **浮动体**：`\caption` 在 figure 内位于 `\includegraphics` 之后、table 内位于
   表体之前；位置约束 `[htbp]`；图文引用先文后图。
6. **交叉引用**：`\label` 紧跟被编号对象；`\eqref`（公式）、`\ref`（章节/图表）、
   `\cite`（文献）各司其职；收敛后无 undefined。
7. **中文排版**：ctex 下标点与字体由模板控制，不手工插入多余空格或 `\quad` 撑版面。

## 5. 工程结构建议（交得可用）

- 主文件 + 章节子文件用 `\input` 划分，导言区集中在主文件；图片统一 `figures/`。
- 交付物必须含全部 `\input`/`\includegraphics`/`.bib`/`.cls` 依赖，使得在干净目录
  中按复现记录一条命令即可编译。
- 不把 PDF 或截图当作“结果”交付：可编辑源码是主产物，PDF 与 PNG 预览是核验证据。
