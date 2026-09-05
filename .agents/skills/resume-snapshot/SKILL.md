---
name: resume-snapshot
description: 通过真实 PDF 管线将当前 ResumeBranch 简历渲染为受限的彩色 PNG 页面图像，用于视觉检查。回答当前页面的分页、间距、对齐、溢出、层次、密度或整体外观判断前应使用本 Skill；纯文本问题不应使用。
metadata:
  version: "1.1.0"
  compatibility: ResumeBranch 后端、Python 3.11 及以上版本、PDF 渲染依赖与 Poppler。
  entrypoint: scripts/run.py:run
  tool-name: resume_snapshot
  tool-input-schema: references/tool-input.schema.json
  runtime-context-schema: references/runtime-context.schema.json
  output-schema: references/output.schema.json
---

# 简历快照

使用与导出相同的 PDF 生成器渲染当前简历的临时视觉快照。本 Skill 只读，不会创建数据库记录、用户可见文件，也不会创建包含图像的消息或日志。

## 使用边界

- 回答需要有关真实页面、分页、留白、对齐、溢出、视觉层次、密度、一致性或整体外观的证据时，使用本 Skill。
- 需要快照时，不得仅根据排版配置或简历文本推断这些属性。
- 纯内容问题不使用本 Skill。
- 如果当前轮已经有快照，不得再次调用。

## 完成契约

加载本 Skill 不代表已经看过页面。若本轮结论依赖当前页面的视觉效果，读取说明后必须调用 `resume_snapshot` 取得真实页面图像，再根据图像作答；不得把排版配置数值当作页面视觉证据。若问题只是在询问如何操作界面、如何理解一个排版字段，或并不依赖页面视觉，可不调用。

## 调用方式

模型只能提供[工具输入 Schema](references/tool-input.schema.json) 中定义的可选原因。简历数据、排版配置、照片、临时浏览器渲染样式和渲染限制，是由图编排程序根据[运行时上下文 Schema](references/runtime-context.schema.json) 提供的可信输入。

入口保留现有限制：最多两页、默认 96 DPI、限制图像边长，并限制 PNG 总字节数。它返回临时多模态图像部件，以及[输出 Schema](references/output.schema.json) 中描述的非敏感诊断信息。将这些图像视为当前渲染效果的证据，不得将其视为新的简历事实。
