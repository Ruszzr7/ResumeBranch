# ResumeBranch Agent 核心评测报告

- 数据集：`agent-core-total-700`，700 条唯一评测案例
- 分类：路由 200 条、Skill 选择 400 条、修改安全 100 条

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

- `confirm_endpoint`：正确 28，错误 0
- `conversation_llm`：正确 134，错误 0
- `direct_edit`：正确 38，错误 0

### 路由混淆矩阵

| 金标 \ 实际 | confirm_endpoint | conversation_llm | direct_edit |
|---|---:|---:|---:|
| confirm_endpoint | 28 | 0 | 0 |
| conversation_llm | 0 | 134 | 0 |
| direct_edit | 0 | 0 | 38 |

### 修改安全计数

- 目标字段：77/77 正确。
- 非目标叶子字段：0/31556 发生变化；连带修改案例 0/100。
- 确认前写入：0/100。
- 取消后保持：19/19。
- 过期确认拦截：19/19。

## 在线 Skill 结果

- `resume_edit`：Precision 99.23%，Recall 97.73% （TP=129，FP=1，FN=3，TN=263）
- `resume_snapshot`：Precision 100.00%，Recall 97.83% （TP=90，FP=0，FN=2，TN=304）
- `resume_coach`：Precision 96.77%，Recall 100.00% （TP=60，FP=2，FN=0，TN=337）
- Skill 总案例：400；进入 LLM Skill 决策：400；排除：0。
- 修改可执行率：100.00% （135/135）
- 修改结果准确率：100.00% （74/74）

## 失败案例

- `skill-v3-046`：{"id": "skill-v3-046", "required_tools": ["resume_edit"], "optional_tools": [], "accepted_outcomes": [], "predicted_tools": ["resume_coach"]}
- `skill-v3-050`：{"id": "skill-v3-050", "required_tools": ["resume_edit"], "optional_tools": [], "accepted_outcomes": [], "predicted_tools": []}
- `skill-v3-063`：{"id": "skill-v3-063", "required_tools": ["resume_edit"], "optional_tools": [], "accepted_outcomes": [], "predicted_tools": []}
- `skill-v3-081`：{"id": "skill-v3-081", "required_tools": ["resume_snapshot"], "optional_tools": [], "accepted_outcomes": [], "predicted_tools": []}
- `skill-v3-084`：{"id": "skill-v3-084", "required_tools": [], "optional_tools": [], "accepted_outcomes": [], "predicted_tools": ["resume_coach"]}
- `skill-v4-059`：{"id": "skill-v4-059", "required_tools": ["resume_edit", "resume_snapshot"], "optional_tools": [], "accepted_outcomes": [], "predicted_tools": ["resume_edit"]}
- `skill-coach-089`：{"id": "skill-coach-089", "required_tools": [], "optional_tools": [], "accepted_outcomes": [], "predicted_tools": ["resume_edit"]}

### 参数可执行失败

- 无

### 目标修改结果失败

- 无

## 说明

所有指标均由实际运行结果计算；在线评测仅使用项目当前对话 API 配置，不读取或输出 API Key。
失败案例不会因分数原因从数据集中删除。
