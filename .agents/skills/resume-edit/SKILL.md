---
name: resume-edit
description: 为用户已明确授权、且目标和结果清晰的 ResumeBranch 简历内容修改或受支持的排版修改生成经过校验的待确认候选。只读建议、视觉检查或尚未确认的事实不应使用本 Skill。
metadata:
  version: "1.1.0"
  compatibility: ResumeBranch 后端、Python 3.11 及以上版本与项目依赖。
  entrypoint: scripts/run.py:run
  tool-name: resume_edit
  tool-input-schema: references/tool-input.schema.json
  runtime-context-schema: references/runtime-context.schema.json
  output-schema: references/output.schema.json
---

# 简历修改

为现有的预览与确认机制生成确定性候选。本 Skill 永远不会保存简历。

## 使用边界

- 用户已明确授权一项具体的简历内容修改，或对话可支持的排版修改时，使用本 Skill。
- 如果目标、引用的建议、事实或预期结果不清晰，先只提出一个聚焦的澄清问题。
- 仅分析请求、普通问题、字体名称或字体文件修改、CSS、坐标或任意新字段不应使用本 Skill。

## 完成契约

加载本 Skill 只表示已获得操作说明，不表示已经执行修改或生成预览。读取本说明后：

- 如果修改目标清晰且用户已授权，必须构造符合输入 Schema 的操作并调用 `resume_edit`；不得仅描述准备如何修改就结束回复。
- 如果必要信息不足或目标无法可靠地唯一定位，不调用工具，只提出一个聚焦的澄清问题。
- 如果本 Skill 并不适用，可以不调用工具，但不得声称或暗示已经产生修改、候选、预览或确认窗。
- 不得把计划调用工具、已构造操作或已加载说明表述为已完成执行。
- 只有 `resume_edit` 成功返回有效候选后，才能告知用户已生成修改预览。如果没有成功候选，不得声称或暗示预览、确认窗或待确认修改已经存在。

## 调用方式

模型只提供[工具输入 Schema](references/tool-input.schema.json) 中定义的字段。当前简历数据、排版、任务上下文和基础版本是由[运行时上下文 Schema](references/runtime-context.schema.json) 定义的可信运行时输入；不得重建它们或将它们作为工具参数提交。

对每个操作：

- 只使用 `set`、`replace`、`append`、`insert`、`remove` 或 `move`。
- 使用当前系统上下文中已提供的 ResumeBranch 简历/排版契约所定义的路径和值结构。
- `set`、`replace` 必须指向当前契约中的最小可写字段；不得整体替换简历根栏目、经历条目、内容块或其他结构化对象。多字段修改应拆成多条操作。
- 新增、删除或排序列表项时，分别使用 `append`/`insert`、`remove`、`move`；不得用整体对象替换模拟这些操作。
- 受支持的排版修改包括页边距、行距、模块间距、模块顺序和契约列出的语义字号；字号仅能按 0.5pt 步进修改指定角色，不能修改字体名称、字体文件、CSS 或坐标。
- 只提交本次请求中已明确授权的操作，永远不得提交完整简历或排版对象。
- 如果一项修改在可执行操作之外还需要独立回答或必要澄清，将其放入 `answer_text`；纯修改请求将其留空。

入口会校验操作数量、路径范围、语义目标、值结构、排版能力和基础版本。输出遵循[输出 Schema](references/output.schema.json)，并必须交给现有确认机制。不得声称候选已被保存或应用。
