"""Deterministic resume diff and selective-apply helpers.

The edit executor returns a complete normalized candidate assembled from
validated operations.  This module compares that candidate with the persisted
resume so the existing confirmation UI can preview and selectively apply
changes without asking the model to make another decision.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Iterable


SECTION_LABELS = {
    "basics": "基础信息",
    "education": "教育经历",
    "education_supplement": "教育经历补充",
    "research_interests": "研究方向",
    "honors": "主要荣誉",
    "publications": "论文",
    "work_experience": "工作经历",
    "internship_experience": "实习经历",
    "project_experience": "项目经历",
    "custom_sections": "自定义模块",
    "others": "专业技能与补充信息",
    "self_evaluation": "自我评价",
}

FIELD_LABELS = {
    "name": "姓名", "gender": "性别", "age": "年龄", "birth_date": "出生年月", "phone": "手机",
    "email": "邮箱", "location": "所在地", "target_position": "目标岗位",
    "photo": "头像", "additional_fields": "补充信息", "value": "内容",
    "school": "学校", "school_name": "学校名称", "degree": "学历", "major": "专业", "date_range": "时间",
    "start_date": "开始时间", "end_date": "结束时间",
    "graduation_date": "毕业时间", "gpa": "GPA", "gpa_scale": "GPA 满分",
    "ranking": "排名", "company_name": "公司",
    "company": "公司", "job_title": "职位", "position": "职位",
    "job_type": "工作类型", "project_name": "项目名称", "role": "角色",
    "details": "详细内容", "skills": "技能", "certificates": "证书",
    "languages": "语言", "school_tags": "学校标签", "theses": "论文",
    "education_supplement": "教育经历补充",
    "title": "标题", "content": "内容", "content_blocks": "内容结构",
    "label": "小标题", "label_bold": "小标题加粗", "text": "正文",
    "items": "条目", "type": "内容类型",
}

VALUE_LABELS = {
    "paragraph": "段落",
    "paragraphs": "分段",
    "bullet": "分点",
    "bullets": "分点",
    "bullet_list": "分点",
    "numbered": "编号",
    "numbered_list": "编号",
    "introduction": "项目简介",
    "responsibilities": "项目职责",
    "generic": "普通内容",
    "standalone": "独立栏目",
}

ATOMIC_LIST_FIELDS = {
    "details", "skills", "certificates", "languages", "school_tags",
    "theses", "self_evaluation",
}

CHANGE_CONTRACT_VERSION = 1


def resume_digest(data: dict) -> str:
    payload = json.dumps(data or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _display_value(value: Any, field_key: str = "") -> str:
    if value in (None, "", []):
        return "未填写"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, list):
        rendered = []
        for item in value:
            rendered.append(_display_value(item))
        return "；".join(rendered) if rendered else "未填写"
    if isinstance(value, dict):
        rendered = []
        for key, item in value.items():
            label = FIELD_LABELS.get(str(key), "内容")
            rendered.append(f"{label}：{_display_value(item, str(key))}")
        return "；".join(rendered) if rendered else "未填写"
    return VALUE_LABELS.get(str(value), str(value))


def _is_blank(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _change_label(path: list[Any]) -> tuple[str, str]:
    section_key = str(path[0]) if path else ""
    section = SECTION_LABELS.get(section_key, "简历内容" if section_key else "简历")
    record = ""
    if len(path) > 1 and isinstance(path[1], int):
        record = f" {path[1] + 1}"
    field_key = str(path[-1]) if path else ""
    field = FIELD_LABELS.get(field_key, "简历字段")
    label = f"{section}{record} · {field}" if field and field != section_key else f"{section}{record}"
    return section, label


def build_resume_changes(before: dict, after: dict) -> list[dict]:
    """Return stable, user-readable leaf changes between two resume snapshots."""
    changes: list[dict] = []

    def add(path: list[Any], old: Any, new: Any, operation: str) -> None:
        if _is_blank(old) and _is_blank(new):
            return
        section, label = _change_label(path)
        changes.append({
            "id": f"change-{len(changes) + 1}",
            "path": path,
            "section": section,
            "label": label,
            "before": deepcopy(old),
            "after": deepcopy(new),
            "before_display": _display_value(old, str(path[-1]) if path else ""),
            "after_display": _display_value(new, str(path[-1]) if path else ""),
            "operation": operation,
        })

    def walk(old: Any, new: Any, path: list[Any]) -> None:
        if old == new:
            return
        if isinstance(old, dict) and isinstance(new, dict):
            for key in sorted(set(old) | set(new)):
                if key not in new:
                    add(path + [key], old[key], None, "remove")
                elif key not in old:
                    add(path + [key], None, new[key], "add")
                else:
                    walk(old[key], new[key], path + [key])
            return
        if isinstance(old, list) and isinstance(new, list):
            field = str(path[-1]) if path else ""
            if field in ATOMIC_LIST_FIELDS or all(not isinstance(item, dict) for item in old + new):
                add(path, old, new, "replace")
                return
            shared = min(len(old), len(new))
            for index in range(shared):
                walk(old[index], new[index], path + [index])
            for index in range(shared, len(new)):
                add(path + [index], None, new[index], "add")
            for index in range(len(old) - 1, len(new) - 1, -1):
                add(path + [index], old[index], None, "remove")
            return
        add(path, old, new, "replace")

    walk(before or {}, after or {}, [])
    return changes


def validate_resume_change_set(before: dict, after: dict, changes: Iterable[dict]) -> bool:
    """Verify that a persisted change list describes the supplied candidate.

    Confirmation records live longer than a single request.  Recomputing the
    leaf changes before selective apply prevents a stale or manually altered
    record from writing an unrelated path into the resume.
    """
    expected = build_resume_changes(before or {}, after or {})
    expected_by_path = {
        json.dumps(item.get("path", []), ensure_ascii=False, sort_keys=True): item
        for item in expected
    }
    seen: set[str] = set()
    for change in changes or []:
        if not isinstance(change, dict) or change.get("kind") == "layout":
            continue
        path = change.get("path")
        key = json.dumps(path if isinstance(path, list) else [], ensure_ascii=False, sort_keys=True)
        expected_change = expected_by_path.get(key)
        if expected_change is None or key in seen:
            return False
        if change.get("operation") != expected_change.get("operation"):
            return False
        if change.get("before") != expected_change.get("before"):
            return False
        if change.get("after") != expected_change.get("after"):
            return False
        seen.add(key)
    return True


def apply_resume_changes(base: dict, changes: Iterable[dict], selected_ids: Iterable[str]) -> dict:
    """Apply only selected deterministic changes to a defensive copy of base."""
    selected = set(selected_ids)
    result = deepcopy(base or {})
    chosen = [change for change in changes if change.get("id") in selected]

    # List removals must run from the highest index down to preserve paths.
    chosen.sort(
        key=lambda item: (
            item.get("operation") != "remove",
            -next((part for part in reversed(item.get("path", [])) if isinstance(part, int)), -1),
        )
    )

    for change in chosen:
        path = list(change.get("path") or [])
        if not path:
            result = deepcopy(change.get("after") or {})
            continue
        parent: Any = result
        for position, part in enumerate(path[:-1]):
            if isinstance(part, int):
                while len(parent) <= part:
                    parent.append({})
                parent = parent[part]
            else:
                if part not in parent or not isinstance(parent[part], (dict, list)):
                    next_part = path[position + 1]
                    parent[part] = [] if isinstance(next_part, int) else {}
                parent = parent[part]
        leaf = path[-1]
        if change.get("operation") == "remove":
            if isinstance(parent, list) and isinstance(leaf, int) and leaf < len(parent):
                parent.pop(leaf)
            elif isinstance(parent, dict):
                parent.pop(leaf, None)
        elif isinstance(parent, list) and isinstance(leaf, int):
            if leaf < len(parent):
                parent[leaf] = deepcopy(change.get("after"))
            else:
                parent.append(deepcopy(change.get("after")))
        else:
            parent[leaf] = deepcopy(change.get("after"))
    return result
