"""第二层：逻辑关联（大模型）。

- 模型与密钥只从环境变量读取：ANTHROPIC_API_KEY、ANTHROPIC_MODEL。
- 结构化输出：定义 submit_analysis 工具（strict: true，参数严格符合 schema）。
  claude-opus-5-5 不支持强制 tool_choice（type "tool"/"any" 返回 400），所以用 auto，
  并在 system prompt 中要求必须调用该工具；没有调用工具也算校验失败。
- 后端再用 pydantic 校验一次（含“引用的新闻编号必须存在”），失败重试 1 次，仍失败抛 LLMError。
- 开启服务端 refusal fallback：模型因安全策略拒答时，由 API 自动换模型重跑。
"""
import json
import logging
import os
from typing import Literal

import anthropic
from pydantic import BaseModel, ValidationError, field_validator

log = logging.getLogger(__name__)

TOOL_NAME = "submit_analysis"
MAX_ATTEMPTS = 2  # 首次 + 重试 1 次


class LLMError(Exception):
    pass


class LogicChain(BaseModel):
    claim: str
    evidence_ids: list[str]
    confidence: Literal["high", "medium", "low"]


class Analysis(BaseModel):
    logic_chains: list[LogicChain]
    summary: str
    caveats: list[str]

    @field_validator("summary")
    @classmethod
    def _summary_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("summary 不能为空")
        return v


def validate_analysis(data: dict, news_ids: set[str]) -> Analysis:
    """pydantic 结构校验 + 引用校验。失败抛 ValueError / ValidationError。"""
    analysis = Analysis.model_validate(data)
    for i, chain in enumerate(analysis.logic_chains):
        if not chain.evidence_ids:
            raise ValueError(f"logic_chains[{i}] 没有引用任何新闻编号")
        unknown = [e for e in chain.evidence_ids if e not in news_ids]
        if unknown:
            raise ValueError(f"logic_chains[{i}] 引用了不存在的新闻编号：{unknown}")
    return analysis


TOOL = {
    "name": TOOL_NAME,
    "description": "提交两只标的的逻辑关联分析结果。这是输出结果的唯一方式。",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "logic_chains": {
                "type": "array",
                "description": "逻辑链列表。没有依据时为空数组。",
                "items": {
                    "type": "object",
                    "properties": {
                        "claim": {"type": "string", "description": "一条逻辑关联的陈述"},
                        "evidence_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "支撑该陈述的新闻编号，如 N1、N3，至少一个",
                        },
                        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    },
                    "required": ["claim", "evidence_ids", "confidence"],
                    "additionalProperties": False,
                },
            },
            "summary": {"type": "string", "description": "总体结论"},
            "caveats": {
                "type": "array",
                "items": {"type": "string"},
                "description": "局限与注意事项",
            },
        },
        "required": ["logic_chains", "summary", "caveats"],
        "additionalProperties": False,
    },
}

SYSTEM_PROMPT = f"""你是一名证券研究助理，负责梳理两只标的之间的统计相关性与基于新闻的逻辑关联。只做事实与逻辑梳理。

规则：
1. 只能基于用户消息中提供的新闻和统计数据推理，不得使用其他外部信息或记忆中的事实。
2. 每条逻辑链必须在 evidence_ids 中引用至少一条新闻编号（如 N1），且只能引用提供的编号。
3. 找不到依据时，logic_chains 留空，并在 summary 中明确写出“未发现直接关联”。
4. 不得输出买卖建议、目标价、仓位建议或未来走势预测。
5. 统计数字只能原样引用提供的数值，不得自行计算、四舍五入或修改。
6. 所有文字用简体中文。
7. 必须且只能通过调用 {TOOL_NAME} 工具提交结果，不要输出其他文字。"""


def build_user_prompt(stats: dict, news: list[dict], news_notes: list[str]) -> str:
    stats_for_prompt = {k: v for k, v in stats.items() if k != "computed_at"}
    lines = [
        "## 统计数据（第一层，已由代码计算，原样引用）",
        "```json",
        json.dumps(stats_for_prompt, ensure_ascii=False, indent=1),
        "```",
        "",
        "## 新闻",
    ]
    if news:
        for n in news:
            lines.append(
                f"[{n['id']}] 标的：{n['name']}（{n['symbol']}.{n['market']}）｜{n['published_at']}｜{n['source']}"
            )
            lines.append(f"标题：{n['title']}")
            if n.get("content"):
                lines.append(f"内容：{n['content']}")
            lines.append("")
    else:
        lines.append("（无）")
    for note in news_notes:
        lines.append(f"注：{note}")
    a, b = stats["a"], stats["b"]
    lines += [
        "",
        f"请分析 {a['name']}（{a['symbol']}.{a['market']}）与 {b['name']}（{b['symbol']}.{b['market']}）"
        f"之间的逻辑关联，并调用 {TOOL_NAME} 提交。",
    ]
    return "\n".join(lines)


def _model() -> str:
    model = os.getenv("ANTHROPIC_MODEL")
    if not model:
        raise LLMError("未设置环境变量 ANTHROPIC_MODEL")
    return model


def _call(client: anthropic.Anthropic, user_prompt: str) -> dict:
    """调用一次模型，返回 submit_analysis 的 input；没有拿到时抛 ValueError。"""
    response = client.beta.messages.create(
        model=_model(),
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        tools=[TOOL],
        tool_choice={"type": "auto"},
        output_config={"effort": "medium"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": user_prompt}],
    )
    log.info("Claude 返回 stop_reason=%s model=%s request_id=%s",
             response.stop_reason, response.model, response._request_id)
    if response.stop_reason == "refusal":
        raise ValueError("模型拒绝回答")
    if response.stop_reason == "max_tokens":
        raise ValueError("输出被 max_tokens 截断")
    for block in response.content:
        if block.type == "tool_use" and block.name == TOOL_NAME:
            return block.input if isinstance(block.input, dict) else json.loads(block.input)
    raise ValueError(f"模型没有调用 {TOOL_NAME} 工具")


def analyze(stats: dict, news: list[dict], news_notes: list[str],
            client: anthropic.Anthropic | None = None) -> dict:
    """返回校验通过的第二层 JSON（dict）。"""
    client = client or anthropic.Anthropic()
    news_ids = {n["id"] for n in news}
    prompt = build_user_prompt(stats, news, news_notes)
    last_error = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            data = _call(client, prompt)
            return validate_analysis(data, news_ids).model_dump()
        except (ValueError, ValidationError) as e:
            last_error = str(e)
            log.warning("第 %d 次大模型输出校验失败：%s", attempt, last_error)
        except anthropic.APIError as e:
            raise LLMError(f"Claude API 调用失败：{e}") from e
    raise LLMError(f"大模型输出校验失败（已重试）：{last_error}")
