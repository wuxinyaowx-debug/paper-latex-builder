# result.json 输出契约

平台约定：`/app/output/result.json` 必须包含 `case_id` 以及 case.json 中
`output_contract` 声明的**全部原始字段**。`scripts/result_emit.py` 负责装配并校验，
本文件说明各部分的语义与填写纪律。

## 1. 结构总览

```json
{
  "case_id": "<来自 case.json，原样回显>",
  "status": "success | partial | failed",
  "<output_contract 字段 1>": {},
  "<output_contract 字段 2>": {},
  "sources": [],
  "changes": [],
  "uncertainty": [],
  "artifacts": [],
  "build_report": {},
  "limits": []
}
```

- output_contract 字段的语义以 case.json 内的字段说明为准；agent 按说明填充，
  不改变字段名、不增删字段。无法完成的字段填 `null` 并在 `uncertainty` 说明原因，
  result_emit.py 会把缺失字段列入 `missing_contract_fields`。
- `status`：全部契约字段完成且构建通过为 `success`；部分完成或有未决项为
  `partial`；未能产出可用结果为 `failed`。诚实状态优于表面完整。

## 2. 事实与来源映射（sources）

每条事实一个条目，可逐条回溯：

```json
{"fact": "表 1 第二行：方法 A 的准确率为 92.4%",
 "origin": "materials/results.pdf 第 3 页表 1",
 "used_in": "output/main.tex:87"}
```

规则：只登记来自 `/input` 材料的事实；材料外内容一律不写入产物；`used_in` 给出
交付物中的位置（文件:行号），便于复核。

## 3. 修改记录（changes）

每一处对源码的实质性修改：

```json
{"file": "proj/main.tex", "line": 23,
 "before": "\\badsymbol{x}", "after": "\\sym{x}",
 "reason": "triage: undefined_control_sequence (main.log l.23)，命令拼写错误"}
```

`reason` 引用 triage 类别与日志签名，或任务要求条目；格式性微调整批合并为一条。

## 4. 不确定性（uncertainty）

按题目要求**分别说明**三类情况，每条带 `kind` 字段，不得混写：

```json
{"kind": "materials_missing", "issue": "材料未给出实验随机种子", "impact": "表 2 备注留空"}
{"kind": "undecidable", "issue": "两处材料的样本量表述冲突（500 vs 480）",
 "tried": "已对照原文图表，无法裁决", "impact": "正文标注 % TODO(确认)"}
{"kind": "run_failed", "issue": "评测环境无 xelatex，未完成真实编译",
 "tried": "latex_preflight.py 静态核查通过（0 error）", "impact": "编译状态未经引擎验证"}
```

规则：材料缺失、无法判断、运行失败分别标注；逐条写明问题、已尝试的处置、对产物
的影响；产物内对应位置用 `% TODO(确认):` 标注。

## 5. 产物与构建证据（artifacts / build_report）

- `artifacts`：交付物相对 /app/output 的路径清单（.tex、.bib、PDF、PNG 预览）。
- `build_report`：latex_build.py 报告的关键子集——引擎与版本、documentclass、
  轮次、bib 工具、收敛标志、错误/警告计数。这是“复现得了”的直接证据。

## 6. 装配命令

```bash
python "$SKILL_DIR/scripts/result_emit.py" \
    --case /input/case.json --answers /app/work/answers.json \
    --out /app/output/result.json
```

退出码 1 表示契约字段缺失——先补 answers.json 再重跑；确实无法补齐时保留缺失
清单交付，不得以默认值冒充完成。
