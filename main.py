from __future__ import annotations

import argparse
import asyncio
import logging
import os
from dataclasses import replace
from pathlib import Path

from browser_agent import BrowserExpertAgent
from config import Settings, settings as default_settings
from excel_handler import ExcelHandler, ExpertRow
from models import ExpertInfo
from utils import setup_logging

logger = logging.getLogger(__name__)


class CliArgs(argparse.Namespace):
    excel_path: str | None = None
    model: str | None = None
    concurrency: int | None = None
    max_steps: int | None = None
    request_interval: float | None = None
    dry_run: bool = False
    no_resume: bool = False
    headed: bool = False
    headless: bool = False


def build_runtime_settings(args: CliArgs) -> Settings:
    runtime = replace(default_settings)
    if args.excel_path:
        runtime.excel_path = Path(args.excel_path)
    if args.concurrency is not None:
        runtime.concurrency = max(1, args.concurrency)
    if args.max_steps is not None:
        runtime.max_steps = max(1, args.max_steps)
    if args.model:
        runtime.llm_model = args.model
    if args.headed:
        runtime.headless = False
    if args.headless:
        runtime.headless = True
    if args.request_interval is not None:
        runtime.request_interval_seconds = max(0.0, args.request_interval)
    runtime.log_dir.mkdir(parents=True, exist_ok=True)
    runtime.save_conversation_path.mkdir(parents=True, exist_ok=True)
    return runtime


async def run_pipeline(runtime: Settings, dry_run: bool, resume: bool) -> None:
    handler = ExcelHandler(runtime.excel_path)
    experts = handler.read_expert_names()
    pending = experts if not resume else [e for e in experts if not handler.is_completed(e.get("status"))]

    logger.info("总专家数: %s, 待处理: %s", len(experts), len(pending))
    if dry_run:
        logger.info("dry-run 模式，不执行网页采集。")
        return
    if not pending:
        logger.info("没有待处理数据，任务结束。")
        return

    agent = BrowserExpertAgent(runtime)
    semaphore = asyncio.Semaphore(runtime.concurrency)
    write_lock = asyncio.Lock()
    results: list[ExpertInfo] = []

    async def process_one(expert: ExpertRow) -> None:
        async with semaphore:
            expert_name = str(expert["name"])
            # 修复：None 值会转换为字符串 "None"，需要特殊处理
            aff_value = expert.get("affiliation", "")
            if aff_value is None:
                initial_affiliation = ""
            else:
                initial_affiliation = str(aff_value).strip()
                # 过滤掉字面量 "None"、"null" 等无效值
                if initial_affiliation.lower() in ("none", "null", "未提供", "暂无", "未知"):
                    initial_affiliation = ""
            row = int(expert["row"])

            # 首次尝试
            result = await agent.process_expert(expert_name, initial_affiliation)

            # 重试机制：如果失败但提取到了单位信息，使用提取的单位重试
            retry_count = 0
            while (
                result.status == "失败"
                and runtime.retry_on_failure
                and retry_count < runtime.max_retries
                and result.affiliation
                and result.affiliation.strip()
            ):
                retry_count += 1
                logger.info(
                    "首次失败，使用提取的单位信息重试: row=%s name=%s affiliation=%s retry=%s/%s",
                    row,
                    expert_name,
                    result.affiliation,
                    retry_count,
                    runtime.max_retries,
                )
                result = await agent.process_expert(expert_name, result.affiliation.strip())

            result.name = expert_name

            async with write_lock:
                try:
                    handler.write_result(row, result)
                    handler.save()
                    logger.debug("已写入 Excel: row=%s name=%s", row, expert_name)
                except Exception as e:
                    logger.error("写入 Excel 失败: row=%s name=%s error=%s", row, expert_name, e)
                    raise
            results.append(result)
            logger.info("完成: row=%s name=%s status=%s retries=%s", row, expert_name, result.status, retry_count)
            await asyncio.sleep(runtime.request_interval_seconds)

    _ = await asyncio.gather(*(process_one(expert) for expert in pending), return_exceptions=False)

    success = sum(1 for r in results if r.status == "成功")
    failed = sum(1 for r in results if r.status == "失败")
    logger.info("任务完成: 成功=%s 失败=%s", success, failed)


def parse_args() -> CliArgs:
    parser = argparse.ArgumentParser(description="专家信息自动化采集")
    parser.add_argument("--excel-path", default=None, help="输入 Excel 路径")
    parser.add_argument("--model", default=None, help="LLM 模型名，例如 openai_gpt_4o / bu_latest / qwen3.5-flash")
    parser.add_argument("--concurrency", type=int, default=None, help="并发数，默认读取环境配置")
    parser.add_argument("--max-steps", type=int, default=None, help="每个 Agent 最大步骤数")
    parser.add_argument("--request-interval", type=float, default=None, help="每个专家处理后等待秒数")
    parser.add_argument("--dry-run", action="store_true", help="仅读取与统计，不执行采集")
    parser.add_argument("--no-resume", action="store_true", help="不启用断点续采")
    parser.add_argument("--headed", action="store_true", help="显示浏览器窗口（headless=False）")
    parser.add_argument("--headless", action="store_true", help="强制无头模式（headless=True）")
    return parser.parse_args(namespace=CliArgs())


def main() -> None:
    args = parse_args()
    runtime = build_runtime_settings(args)
    setup_logging(
        log_dir=runtime.log_dir,
        level=runtime.log_level,
        console_output=runtime.log_console_output,
        file_output=runtime.log_file_output,
    )
    logger.info(
        "启动参数: excel=%s model=%s concurrency=%s max_steps=%s headless=%s base_url=%s",
        runtime.excel_path,
        runtime.llm_model,
        runtime.concurrency,
        runtime.max_steps,
        runtime.headless,
        runtime.llm_base_url or "默认",
    )

    if not args.dry_run:
        if not runtime.llm_model:
            raise RuntimeError("未找到可用模型，请设置 LLM_MODEL。")
        if runtime.llm_model.startswith("openai_") and not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("当前模型为 OpenAI，但未设置 OPENAI_API_KEY。")
        if runtime.llm_model.startswith("bu_") and not os.getenv("BROWSER_USE_API_KEY"):
            raise RuntimeError("当前模型为 browser-use cloud，但未设置 BROWSER_USE_API_KEY。")
        # 自定义模型名（如 qwen3.5-flash）走 OpenAI 兼容协议
        if (
            not runtime.llm_model.startswith(("openai_", "bu_", "azure_", "google_"))
            and runtime.llm_base_url
            and not (os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY"))
        ):
            raise RuntimeError("自定义模型名 + base_url 模式下，请设置 OPENAI_API_KEY 或 DASHSCOPE_API_KEY。")

    asyncio.run(run_pipeline(runtime, dry_run=args.dry_run, resume=not args.no_resume))


if __name__ == "__main__":
    main()
