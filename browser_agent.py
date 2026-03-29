from __future__ import annotations

import json
import logging
import math
import os
import re
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

os.environ.setdefault("BROWSER_USE_CONFIG_DIR", str(Path.cwd() / ".browseruse"))

from browser_use import Agent, Browser, Controller
from browser_use.agent.views import ActionResult, AgentHistoryList
from browser_use.llm.models import get_llm_by_name
from browser_use.llm.openai.chat import ChatOpenAI

from config import Settings
from models import ExpertInfo
from prompts.task_prompt import build_task_prompt
from search_strategy import generate_queries
from utils import clean_text, normalize_email

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _VisionAdaptiveState:
    width: int
    height: int
    detail: Literal["auto", "low", "high"] = "auto"
    retries: int = 0
    max_retries: int = 4


def _initial_llm_screenshot_size(model_name: str | None) -> tuple[int, int]:
    normalized = (model_name or "").lower()
    if "claude" in normalized or "sonnet" in normalized:
        return (1400, 850)
    if "qwen" in normalized or "qvq" in normalized:
        return (1280, 800)
    if "gpt" in normalized or "o3" in normalized or "o4" in normalized:
        return (1360, 840)
    return (1320, 820)


def _clamp_aspect(width: int, height: int, max_ratio: float = 2.4) -> tuple[int, int]:
    if width <= 0 or height <= 0:
        return (1000, 640)

    ratio = width / height
    if ratio > max_ratio:
        width = int(height * max_ratio)
    elif ratio < 1.0 / max_ratio:
        height = int(width * max_ratio)

    width = max(640, width)
    height = max(480, height)
    return (width, height)


def _is_data_uri_size_error(exc: Exception) -> bool:
    text = str(exc).lower()
    patterns = (
        "data-uri",
        "max bytes per data-uri",
        "request too large",
        "payload too large",
        "image too large",
    )
    return any(p in text for p in patterns)


def _extract_limit_bytes(exc: Exception) -> int | None:
    match = re.search(r"max bytes per data-uri item\s*:\s*(\d+)", str(exc), flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None


def _next_adaptive_state(state: _VisionAdaptiveState, exc: Exception) -> _VisionAdaptiveState:
    retries = state.retries + 1
    limit_bytes = _extract_limit_bytes(exc)

    base_factor = 0.86 - 0.08 * math.log2(retries + 1)
    factor = min(0.9, max(0.58, base_factor))

    if limit_bytes is not None and limit_bytes <= 10 * 1024 * 1024:
        factor = min(factor, 0.74)

    next_w = int(state.width * factor)
    next_h = int(state.height * factor)
    next_w, next_h = _clamp_aspect(next_w, next_h)
    next_detail = "low" if retries >= 2 else "auto"

    return _VisionAdaptiveState(
        width=next_w,
        height=next_h,
        detail=next_detail,
        retries=retries,
        max_retries=state.max_retries,
    )


def _normalize_info(result: ExpertInfo) -> ExpertInfo:
    normalized = result.model_copy()
    normalized.biography = clean_text(normalized.biography)
    normalized.affiliation = clean_text(normalized.affiliation)

    # 清理邮箱：过滤无效值
    email = clean_text(normalized.email)
    invalid_patterns = ["未公布", "暂无", "无", "null", "none", "-", "—", "未提供", "未公开", "保密", "待更新"]
    if email and any(pattern in email.lower() for pattern in invalid_patterns):
        email = None
    normalized.email = normalize_email(email) if email else None

    # 清理电话：过滤无效值
    phone = clean_text(normalized.phone)
    if phone and any(pattern in phone.lower() for pattern in invalid_patterns):
        phone = None
    normalized.phone = phone if phone else None

    normalized.notes = clean_text(normalized.notes)
    normalized.source_urls = [u.strip() for u in normalized.source_urls if u and u.strip()]
    return normalized


def _with_status(result: ExpertInfo) -> ExpertInfo:
    """判断专家信息提取状态

    成功标准：
    - 必须有工作单位
    - 必须有简介
    - 必须有邮箱或电话至少一个
    """
    normalized = _normalize_info(result)

    has_affiliation = bool(normalized.affiliation and normalized.affiliation.strip())
    has_biography = bool(normalized.biography and normalized.biography.strip())
    has_contact = bool(normalized.email) or bool(normalized.phone)

    # 成功：必须有单位 + 简介 + 联系方式
    if has_affiliation and has_biography and has_contact:
        normalized.status = "成功"
    else:
        normalized.status = "失败"
        # 在备注中说明缺少什么
        missing = []
        if not has_affiliation:
            missing.append("单位")
        if not has_biography:
            missing.append("简介")
        if not has_contact:
            missing.append("邮箱/电话")
        if missing:
            existing_notes = normalized.notes or ""
            normalized.notes = f"{existing_notes} | 缺少: {', '.join(missing)}" if existing_notes else f"缺少: {', '.join(missing)}"

    return normalized


def create_controller(settings: Settings) -> Controller:
    controller = Controller()
    controller.exclude_action("search")

    @controller.action(
        "Search the web with Baidu only. Input should be the search query string.",
        terminates_sequence=True,
    )
    async def baidu_search(query: str, browser_session):
        encoded_query = urllib.parse.quote_plus(query)
        search_url = f"https://www.baidu.com/s?wd={encoded_query}"
        return await controller.navigate(url=search_url, new_tab=False, browser_session=browser_session)

    @controller.action(
        "当你收集到足够的专家信息后，调用此 action 提交最终结果",
        param_model=ExpertInfo,
    )
    async def submit_expert_info(params: ExpertInfo):
        finalized = _with_status(params)
        return ActionResult(
            is_done=True,
            success=finalized.status != "失败",
            extracted_content=finalized.model_dump_json(),
            long_term_memory=f"已提交专家信息: {finalized.name}",
        )

    return controller


def _enrich_failure_notes(expert: ExpertInfo, final_result: str | None, judgement: dict[str, object] | None = None) -> ExpertInfo:
    """为失败的专家信息补充详细备注"""
    if expert.status != "失败":
        return expert

    notes_parts = []

    # 优先使用 Judge 的 failure_reason
    if judgement:
        failure_reason_raw = judgement.get("failure_reason")
        if failure_reason_raw:
            failure_reason = str(failure_reason_raw)
            # 限制长度，避免过长
            if len(failure_reason) > 800:
                failure_reason = failure_reason[:800] + "..."
            notes_parts.append(f"失败原因: {failure_reason}")

        # 如果有 impossble_task 标记，也记录
        if judgement.get("impossible_task"):
            notes_parts.append("任务判定为不可能完成")

    # 如果没有 Judge failure_reason，尝试从 final_result 中提取
    if not notes_parts and final_result:
        # 提取关键信息片段
        if "=== FINDINGS ===" in final_result:
            findings_start = final_result.find("=== FINDINGS ===")
            findings_end = final_result.find("=== ", findings_start + 20)
            if findings_end == -1:
                findings_end = final_result.find("\n\n", findings_start)
            if findings_end != -1:
                findings = final_result[findings_start:findings_end].strip()
                # 限制长度
                if len(findings) > 400:
                    findings = findings[:400] + "..."
                notes_parts.append(f"搜索结果: {findings}")

        # 提取结论
        if "=== CONCLUSION ===" in final_result:
            conclusion_start = final_result.find("=== CONCLUSION ===")
            conclusion_end = final_result.find("\n\n", conclusion_start)
            if conclusion_end == -1:
                conclusion_end = conclusion_start + 300
            conclusion = final_result[conclusion_start + 20:conclusion_end].strip()
            if conclusion:
                notes_parts.append(f"结论: {conclusion}")

    # 检查已提取的字段
    filled = []
    for field in ["biography", "affiliation", "email", "phone"]:
        value = getattr(expert, field, None)
        if value:
            field_label = {
                "biography": "简介",
                "affiliation": "单位",
                "email": "邮箱",
                "phone": "电话"
            }.get(field, field)
            filled.append(field_label)

    if filled:
        notes_parts.append(f"已获取: {', '.join(filled)}")

    # 如果没有任何备注，添加默认消息
    if not notes_parts:
        notes_parts.append("Agent 执行完成但未能提取到有效信息")

    # 合并所有备注
    expert.notes = " | ".join(notes_parts)
    return expert


def parse_agent_result(history: AgentHistoryList[ExpertInfo], expert_name: str) -> ExpertInfo:
    final_result = history.final_result()
    if not final_result:
        return ExpertInfo(name=expert_name, status="失败", notes="Agent 未返回最终结果")

    try:
        parsed = ExpertInfo.model_validate_json(final_result)
    except Exception:
        try:
            parsed = ExpertInfo.model_validate(json.loads(final_result))
        except Exception as exc:
            # 解析失败时，仍然尝试从原始结果中提取信息作为备注
            expert = ExpertInfo(name=expert_name, status="失败")
            return _enrich_failure_notes(expert, final_result, history.judgement())

    if not parsed.name:
        parsed.name = expert_name

    result = _with_status(parsed)

    # 为失败的结果补充详细备注
    if result.status == "失败":
        result = _enrich_failure_notes(result, final_result, history.judgement())

    return result


def build_llm(model_name: str, base_url: str | None = None):
    if not model_name:
        raise RuntimeError("未配置 LLM_MODEL。")

    try:
        llm = get_llm_by_name(model_name)
        if base_url and isinstance(llm, ChatOpenAI):
            llm.base_url = base_url
        return llm
    except ValueError:
        if not base_url:
            raise
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            raise RuntimeError("使用自定义模型名时，请设置 OPENAI_API_KEY 或 DASHSCOPE_API_KEY。")
        return ChatOpenAI(model=model_name, api_key=api_key, base_url=base_url)


class BrowserExpertAgent:
    def __init__(self, settings: Settings):
        self.settings: Settings = settings
        self._llm = None

    def _get_llm(self):
        if self._llm is None:
            self._llm = build_llm(self.settings.llm_model or "", self.settings.llm_base_url)
        return self._llm

    async def process_expert(self, name: str, affiliation: str = "") -> ExpertInfo:
        queries = generate_queries(name, affiliation)
        task = build_task_prompt(name, affiliation, queries)

        init_w, init_h = _initial_llm_screenshot_size(self.settings.llm_model)
        adaptive = _VisionAdaptiveState(width=init_w, height=init_h)

        while True:
            browser = Browser(
                headless=self.settings.headless,
                disable_security=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-extensions",
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-web-security",
                    "--disable-features=IsolateOrigins,site-per-process",
                ],
                minimum_wait_page_load_time=0.5,
                wait_for_network_idle_page_load_time=2.0,
            )
            controller = create_controller(self.settings)
            agent = Agent(
                task=task,
                llm=self._get_llm(),
                browser=browser,
                controller=controller,
                use_vision=True,
                vision_detail_level=adaptive.detail,
                llm_screenshot_size=(adaptive.width, adaptive.height),
                max_actions_per_step=self.settings.max_actions_per_step,
                save_conversation_path=str(self.settings.save_conversation_path) if self.settings.save_conversations else None,
                extend_system_message=(
                    "When a web search is needed, do not call the search action. "
                    "Always use baidu_search(query=...) and continue from Baidu result pages."
                ),
            )

            try:
                history = await agent.run(max_steps=self.settings.max_steps)
                return parse_agent_result(history, name)
            except Exception as exc:
                if _is_data_uri_size_error(exc) and adaptive.retries < adaptive.max_retries:
                    next_state = _next_adaptive_state(adaptive, exc)
                    logger.warning(
                        "视觉负载自适应重试: expert=%s retry=%s size=%sx%s detail=%s -> %sx%s detail=%s",
                        name,
                        adaptive.retries + 1,
                        adaptive.width,
                        adaptive.height,
                        adaptive.detail,
                        next_state.width,
                        next_state.height,
                        next_state.detail,
                    )
                    adaptive = next_state
                    continue

                logger.exception("处理专家失败: %s", name)
                exc_type = type(exc).__name__
                exc_msg = str(exc)
                if len(exc_msg) > 200:
                    exc_msg = exc_msg[:200] + "..."
                notes = f"执行异常: {exc_type} - {exc_msg}"
                return ExpertInfo(name=name, status="失败", notes=notes)
            finally:
                try:
                    await agent.close()
                except Exception:
                    logger.debug("关闭 agent 时发生非致命异常", exc_info=True)
