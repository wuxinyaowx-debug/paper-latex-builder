# 最小调用示例（示例，非正式案例结果）

> 本目录是 Skill 接口演示：输入、调用方式与示意输出。**所有输出均为示例，不冒充
> 平台正式案例结果。**

## 输入

`main.tex`：一个含两处典型问题的最小工程——

1. 第 24 行 `\toprule`：因导言区注释掉了 `\usepackage{booktabs}`，触发
   `undefined_control_sequence`（P1）；
2. 第 13 行 `\ref{sec:nosuchlabel}`：无对应 `\label`，触发
   `undefined_reference`（P2，多轮不消说明 label 缺失）。

## 调用

```bash
# 0. 静态预检（无需 TeX）：立即报出 [error|ref_missing] main.tex:13
python ../../scripts/latex_preflight.py --project . --text

# 1. 构建（需 TeX 环境）：预期 status=errors，引擎 pdflatex，1–2 轮
python ../../scripts/latex_build.py --project . --report /tmp/demo-build.json

# 2. 分诊：预期 fix_queue 前两条
python ../../scripts/latex_log_triage.py main.log --text
# [P1|undefined_control_sequence] ./main.tex:24 -- Undefined control sequence (\toprule)
# [P2|undefined_reference]        ./main.tex:13 -- Reference 'sec:nosuchlabel' undefined
```

## 示意输出（示例）

修复策略演示：

- P1：在导言区恢复 `\usepackage{booktabs}`，changes 记录
  `{file: main.tex, line: 3, before: "% 故意缺失...", after: "\\usepackage{booktabs}",
   reason: "triage: undefined_control_sequence, main.log l.24 \\toprule"}`；
- P2：多轮编译后 `sec:nosuchlabel` 仍未定义 → 确认非轮次问题，正文改为引用存在的
  标签或删除该引用，并记 changes；
- 重跑 latex_build.py → `status=success, converged=true`；
- result_emit.py 装配时 sources/changes/uncertainty 齐备。

无 TeX 环境时 latex_build.py 如实返回 `status=environment_error` 并注明缺引擎——
这正是 Skill 的异常处置行为（禁止伪造编译成功）。
