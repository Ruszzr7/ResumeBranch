"""Five-case real-LLM smoke test using synthetic resume/JD data only."""

import asyncio
import re
import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.harness.interview import run_interview_turn
from backend.resume_agent import LLM_ENABLED, conversation_llm


SYNTHETIC_RESUME = {
    "basics": {
        "name": "测试候选人", "gender": "", "phone": "", "email": "",
        "target_position": "产品经理",
    },
    "education": [],
    "work_experience": [{
        "company_name": "示例科技", "job_title": "产品实习生",
        "date_range": ["2025.01", "2025.06"], "job_type": "实习",
        "details": ["参与新用户落地页优化。"],
    }],
    "project_experience": [],
    "others": {"skills": ["SQL"], "certificates": [], "languages": []},
    "self_evaluation": [],
}

SYNTHETIC_JD = {
    "company": "示例公司",
    "position": "增长产品经理",
    "requirements": ["A/B 测试", "数据分析", "增长实验"],
}


async def main():
    if not LLM_ENABLED:
        raise RuntimeError("当前 LLM 未配置，无法执行真实模型冒烟测试")
    original = deepcopy(SYNTHETIC_RESUME)
    async def start_case(mode, jd_data, request_id):
        return await run_interview_turn(
            llm=conversation_llm,
            action="start",
            mode=mode,
            user_text="请开始分析合成测试简历。",
            resume_data=SYNTHETIC_RESUME,
            jd_data=jd_data,
            memory={},
            workflow={},
            request_id=request_id,
        )

    diagnosis, coaching, jd_review = await asyncio.gather(
        start_case("diagnosis", {}, "synthetic-diagnosis"),
        start_case("coaching", {}, "synthetic-coaching-no-jd"),
        start_case("jd_review", SYNTHETIC_JD, "synthetic-jd-review"),
    )
    for result in (diagnosis, coaching, jd_review):
        assert result["content"].count("？") == 1, result["content"]

    no_number_answer = "我参与了落地页优化，负责用 SQL 跟踪注册漏斗并整理实验报告。"
    quantified_answer = "我设计了两版落地页并跟踪注册漏斗，实验覆盖12000名新用户，注册转化率从8%提升到10%。"
    no_number_result, quantified_result = await asyncio.gather(
        run_interview_turn(
            llm=conversation_llm,
            action="answer",
            mode="coaching",
            user_text=no_number_answer,
            resume_data=SYNTHETIC_RESUME,
            jd_data={},
            memory=coaching["memory"],
            workflow=coaching["workflow_updates"],
            request_id="synthetic-no-number-answer",
        ),
        run_interview_turn(
            llm=conversation_llm,
            action="answer",
            mode="jd_review",
            user_text=quantified_answer,
            resume_data=SYNTHETIC_RESUME,
            jd_data=SYNTHETIC_JD,
            memory=jd_review["memory"],
            workflow=jd_review["workflow_updates"],
            request_id="synthetic-quantified-answer",
        ),
    )
    assert no_number_result["content"].count("？") == 1, no_number_result["content"]
    assert quantified_result["content"].count("？") == 1, quantified_result["content"]
    no_number_facts = " ".join(
        fact["claim"] for fact in no_number_result["memory"]["verified_facts"]
    )
    assert not re.search(r"\d", no_number_facts), no_number_facts
    assert quantified_result["memory"]["verified_facts"], "模型没有提取任何可追溯事实"
    for fact in quantified_result["memory"]["verified_facts"]:
        assert fact["source_quote"] in quantified_answer
        assert fact["claim"] == fact["source_quote"]

    # Applying a suggestion is intentionally not part of this script; that path
    # is verified through deterministic confirmation tests and manual browser acceptance.
    assert SYNTHETIC_RESUME == original, "只读拷打错误地修改了输入简历"
    print({
        "success": True,
        "cases": ["diagnosis", "coaching", "no_jd", "jd_review", "no_numeric_evidence"],
        "phases": {
            "diagnosis": diagnosis["workflow_updates"]["phase"],
            "coaching": coaching["workflow_updates"]["phase"],
            "jd_review": jd_review["workflow_updates"]["phase"],
            "no_number": no_number_result["workflow_updates"]["phase"],
            "quantified": quantified_result["workflow_updates"]["phase"],
        },
        "no_number_fact_count": len(no_number_result["memory"]["verified_facts"]),
        "quantified_fact_count": len(quantified_result["memory"]["verified_facts"]),
        "suggestion_ready": bool(quantified_result["memory"].get("latest_suggestion")),
    })


if __name__ == "__main__":
    asyncio.run(main())
