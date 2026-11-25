# 交付前自查评分表（编译-修复-交付闭环）

交付每个案例结果前，按本表逐项自查并在 answers.json 的 `notes` 中记录结论。
四项对应赛题关注的四个问题；任何一项"否"都必须进入 `uncertainty` 并说明原因。

## 1. 编译得通

| # | 检查项 | 通过标准 | 证据 |
|-|-|-|-|
| 1.1 | 构建状态 | build-report.json `status=success` 且 `converged=true` | latex_build.py 报告 |
| 1.2 | 错误清零 | triage.json 中无 P0/P1 findings | latex_log_triage.py |
| 1.3 | 轮次稳定 | 重复运行 latex_build.py 两次，轮次数与 aux 签名一致 | 两次报告对比 |
| 1.4 | 根因可追溯 | 每处修复都能引用 triage 类别 + 日志签名（文件:行号） | changes 记录 |

## 2. 改得对

| # | 检查项 | 通过标准 | 证据 |
|-|-|-|-|
| 2.1 | 公式 | 编号与正文 `\eqref` 一一对应；符号、正斜体与材料底稿一致 | 目检 + preflight |
| 2.2 | 表格 | 数值与材料逐格一致；三线表无竖线；无 Overfull hbox | 目检 + 日志 |
| 2.3 | 引用与文献 | 无 undefined reference/citation；`\cite` 键与 .bib 一一对应 | preflight + 日志 |
| 2.4 | 模板必填项 | 题目要求的模板选项、标题/作者/摘要等必填项齐全 | 模板示例对照 |
| 2.5 | 版式抽检 | 首页与关键页 PNG 目检无乱码、无溢出、图表完整 | PDF 渲染工具产物 |

## 3. 交得可用

| # | 检查项 | 通过标准 | 证据 |
|-|-|-|-|
| 3.1 | 可编辑源码 | 交付 .tex/.bib/图片/类文件全套源码，非 PDF 或截图 | artifacts 清单 |
| 3.2 | 依赖齐备 | 干净目录复制后 preflight 无 file_missing | latex_preflight.py |
| 3.3 | 静态健康 | preflight 无 environment/math/ref/citation 类 error | preflight 报告 |
| 3.4 | 标注未决项 | 材料缺口与待确认处有 `% TODO(确认):` 且入 uncertainty | 全文检索 |

## 4. 复现得了

| # | 检查项 | 通过标准 | 证据 |
|-|-|-|-|
| 4.1 | 环境记录 | build_report 含引擎、版本、documentclass、轮次、命令 | build-report.json |
| 4.2 | 命令可重放 | 交付说明含一条可复制的编译命令 | result.json notes |
| 4.3 | 版本边界 | 模板/宏包特殊依赖（版本、获取方式）写明 | README 或 notes |

## 5. 事实与边界（写作任务附加）

| # | 检查项 | 通过标准 | 证据 |
|-|-|-|-|
| 5.1 | 来源映射 | 每个数字/术语/论断可回溯到材料位置（文件+页/行） | sources 逐条 |
| 5.2 | 无材料外事实 | 全文检索不到底稿之外的数字与论断 | 抽查比对 |
| 5.3 | 不确定性三分 | 材料缺失、无法判断、运行失败分别标注，不混写 | uncertainty |
| 5.4 | 契约完整 | result_emit 退出码 0，无 missing_contract_fields | result_emit 输出 |

未通过项处理：能修则回到流程修复；不能修则在 uncertainty 写明问题、已尝试的
处置与影响，并以 `status=partial` 交付——诚实状态优于表面完整。
