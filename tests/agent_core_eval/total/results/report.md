# ResumeBranch Agent 核心评测报告

- 数据集：`agent-core-total-600`，600 条唯一评测案例
- 分类：路由 200 条、Skill 选择 300 条、修改安全 100 条
- 本轮评测调整：修改正确性按最终候选结果判定；操作 JSON 严格匹配仅作为诊断信息，不作为核心指标
- 报告生成时间：2026-08-30T10:47:08.831158+00:00

## 指标定义

- 路由准确率：入口节点预测正确数 / 路由案例数。
- Skill Precision、Recall：只对实际进入 conversation_llm 的案例，以是否调用对应 Skill 进行多标签统计。
- 多合法结果：案例显式列出允许的工具与回答分支，命中任一完整分支即计为有效。
- 修改可执行率：通过工具参数与操作契约校验的修改调用数 / 全部修改调用数。
- 修改结果准确率：在同一基准简历上生成金标候选与实际候选，最终差异符合用户目标的案例数 / 有结果金标的修改案例数。
- 非目标字段误改率：候选中发生变化的非目标叶子字段数 / 检查的非目标叶子字段数；另报发生任意连带修改的案例率。

## 离线结果

- 路由准确率：100.00%（200/200）
- 目标修改成功率：100.00%
- 非目标字段误改率：0.00%
- 未确认写入率：0.00%
- 取消后数据保持率：100.00%
- 过期确认拦截率：100.00%

### 路由各路径

- `conversation_llm`：正确 101，错误 0
- `direct_edit`：正确 40，错误 0
- `interview_coach`：正确 31，错误 0
- `tool_node`：正确 28，错误 0

### 路由混淆矩阵

| 金标 \ 实际 | conversation_llm | direct_edit | interview_coach | tool_node |
|---|---:|---:|---:|---:|
| conversation_llm | 101 | 0 | 0 | 0 |
| direct_edit | 0 | 40 | 0 | 0 |
| interview_coach | 0 | 0 | 31 | 0 |
| tool_node | 0 | 0 | 0 | 28 |

### 修改安全计数

- 目标字段：77/77 正确。
- 非目标叶子字段：0/30956 发生变化；连带修改案例 0/100。
- 确认前写入：0/100。
- 取消后保持：19/19。
- 过期确认拦截：19/19。

## 在线 Skill 结果

- `request_resume_edit`：Precision 98.23%，Recall 98.23% （TP=111，FP=2，FN=2）
- `render_resume_pdf_images`：Precision 95.29%，Recall 100.00% （TP=81，FP=4，FN=0）
- Skill 总案例：300；进入 LLM Skill 决策：300；排除：0。
- 修改可执行率：100.00% （117/117）
- 修改结果准确率：95.83% （69/72）

## 失败案例

- `skill-v3-015`：{"id": "skill-v3-015", "required_tools": ["request_resume_edit"], "optional_tools": [], "accepted_outcomes": [], "predicted_tools": []}
- `skill-v3-026`：{"id": "skill-v3-026", "required_tools": [], "optional_tools": [], "accepted_outcomes": [], "predicted_tools": ["request_resume_edit"]}
- `skill-v3-043`：{"id": "skill-v3-043", "required_tools": ["request_resume_edit"], "optional_tools": [], "accepted_outcomes": [], "predicted_tools": []}
- `skill-v3-050`：{"id": "skill-v3-050", "required_tools": [], "optional_tools": [], "accepted_outcomes": [], "predicted_tools": ["render_resume_pdf_images"]}
- `skill-v3-052`：{"id": "skill-v3-052", "required_tools": [], "optional_tools": [], "accepted_outcomes": [], "predicted_tools": ["request_resume_edit"]}
- `skill-v3-056`：{"id": "skill-v3-056", "required_tools": [], "optional_tools": [], "accepted_outcomes": [], "predicted_tools": ["render_resume_pdf_images"]}
- `skill-v3-064`：{"id": "skill-v3-064", "required_tools": [], "optional_tools": [], "accepted_outcomes": [], "predicted_tools": ["render_resume_pdf_images"]}
- `skill-v4-050`：{"id": "skill-v4-050", "required_tools": [], "optional_tools": [], "accepted_outcomes": [], "predicted_tools": ["render_resume_pdf_images"]}

### 参数可执行失败

- 无

### 目标修改结果失败

- `skill-v3-015`：最终候选未达到金标结果。 未生成可供用户确认的修改候选
- `skill-v3-043`：最终候选未达到金标结果。 未生成可供用户确认的修改候选
- `skill-v4-023`：最终候选未达到金标结果。

## 可用于简历的表述草稿

构建 600 条版本化 Agent 核心评测集，覆盖 LangGraph 路由、Skill 选择与候选修改安全；实现离线可复现指标和在线对话模型评测，量化路由准确率、Skill Precision/Recall、修改可执行率与最终修改正确率，并通过失败归因完善 Agent 行为。

## 说明

所有指标均由实际运行结果计算；在线评测仅使用项目当前对话 API 配置，不读取或输出 API Key。
失败案例不会因分数原因从数据集中删除。
