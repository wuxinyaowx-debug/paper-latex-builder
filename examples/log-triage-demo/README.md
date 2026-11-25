# 错误分诊演示（示例，非正式案例结果）

> 本目录演示 `latex_log_triage.py` 的输入、调用与输出。**demo.log / demo.blg 为人工
> 构造的合成日志，expected-triage.json 为示意输出，均不冒充正式案例结果。**
> 本演示无需 TeX 环境，任何装有 Python 3 的机器可直接复跑核对。

## 输入

- `demo.log`：合成 XeLaTeX 日志，覆盖 7 类典型证据——file-line 错误
  （`./chapters/intro.tex:13: Undefined control sequence.`）、经典 `!` 错误
  （`\toprule`、Missing $）、环境不配对（`\begin{align}` 被 `\end{document}` 闭合）、
  级联 `Emergency stop`、未定义引用与文献、Overfull hbox、fontspec 字体警告；
- `demo.blg`：合成 BibTeX 日志（数据库文件缺失 + 空年份警告）。

## 调用

```bash
python ../../scripts/latex_log_triage.py demo.log --blg demo.blg \
    --out my-triage.json --text
# 对照核对：diff my-triage.json expected-triage.json
```

## 示意输出（示例）

`expected-triage.json`：13 条 findings，按 P0→P3 排成修复队列，要点：

- `[P0|emergency_stop]` 被识别为级联表象，advice 提示先修最早的真实错误；
- `[P1|undefined_control_sequence] ./chapters/intro.tex:13` 与 `l.24 \toprule`
  两处分别定位到文件与行号，后者在 suggested_fix 中点名出错命令 `\toprule`；
- `[P1|environment_error] ./chapters/method.tex:52` 环境不配对；
- `[P1|bibtex_error]` 来自 .blg 的 `I couldn't open database file refs.bib`；
- `[P2|undefined_reference / undefined_citation / rerun_needed]` 归为轮次类，
  提示先补 bib 轮次与额外编译轮次再判断是否真缺 label/条目；
- `[P3|overfull_box]` 版式类单列，不与编译错误混淆。

同一目录下的 `../minimal-broken/` 演示完整编译-修复闭环（需 TeX 环境）。
