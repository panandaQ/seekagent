from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class FieldConfig:
    """字段配置"""
    name: str
    label: str
    description: str
    priority: str = "medium"  # high, medium, low


@dataclass(slots=True)
class Settings:
    # 必需参数（无默认值）
    excel_path: Path
    log_dir: Path
    save_conversation_path: Path
    llm_model: str | None
    llm_base_url: str | None
    max_steps: int
    max_actions_per_step: int
    concurrency: int
    headless: bool
    use_vision: bool
    request_interval_seconds: float
    min_success_fields: int
    partial_success_min_fields: int

    # 可选参数（有默认值）
    retry_on_failure: bool = False
    max_retries: int = 1
    fields: list[FieldConfig] = field(default_factory=list)
    save_conversations: bool = False
    # 日志配置
    log_level: str = "INFO"
    log_console_output: bool = True
    log_file_output: bool = True

    @property
    def OUTPUT_HEADERS(self) -> dict[str, str]:
        """动态生成输出表头，按指定顺序排列"""
        # 先定义固定字段，按用户要求的顺序
        fixed_headers = {
            "name": "姓名",
            "affiliation": "工作单位",
            "biography": "简介",
            "email": "邮箱",
            "phone": "电话",
            "source_urls": "信息来源URL",
            "status": "提取状态",
            "notes": "备注",
        }

        # 添加动态配置的字段（排除已存在的字段）
        for f in self.fields:
            if f.name not in fixed_headers:
                fixed_headers[f.name] = f.label

        return fixed_headers

    @property
    def field_names(self) -> list[str]:
        """获取所有字段名称"""
        return [f.name for f in self.fields]

    @property
    def high_priority_fields(self) -> list[str]:
        """高优先级字段"""
        return [f.name for f in self.fields if f.priority == "high"]

    @classmethod
    def from_yaml(cls, config_path: str | None = None) -> "Settings":
        """从 YAML 文件加载配置"""
        if config_path:
            config_file = Path(config_path)
        else:
            config_file = Path("config.yaml")

        if config_file.exists():
            with open(config_file, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        else:
            config = {}

        # 从配置中读取各部分
        paths = config.get("paths", {})
        llm = config.get("llm", {})
        browser = config.get("browser", {})
        agent = config.get("agent", {})
        execution = config.get("execution", {})
        logging_cfg = config.get("logging", {})

        # 解析字段配置
        fields_cfg = config.get("fields", [])
        fields = [
            FieldConfig(
                name=f.get("name", ""),
                label=f.get("label", ""),
                description=f.get("description", ""),
                priority=f.get("priority", "medium"),
            )
            for f in fields_cfg
            if f.get("name")  # 过滤掉没有 name 的项
        ]

        # 如果配置文件中没有字段定义，使用默认字段
        if not fields:
            fields = [
                FieldConfig("biography", "简介", "教育背景、工作经历、主要成就", "high"),
                FieldConfig("affiliation", "单位", "完整机构名称", "high"),
                FieldConfig("email", "邮箱", "公开邮箱地址", "high"),
                FieldConfig("phone", "电话", "公开办公电话", "medium"),
            ]

        return cls(
            excel_path=Path(paths.get("excel_path", "专家名单-small.xlsx")),
            log_dir=Path(paths.get("log_dir", "logs")),
            save_conversation_path=Path(paths.get("save_conversation_path", "logs/agent_conversations")),
            save_conversations=str(paths.get("save_conversations", "false")).lower() == "true",
            llm_model=llm.get("model") or cls._default_llm_model(config),
            llm_base_url=llm.get("base_url"),
            max_steps=int(agent.get("max_steps", 40)),
            max_actions_per_step=int(agent.get("max_actions_per_step", 5)),
            concurrency=max(1, int(execution.get("concurrency", 2))),
            headless=str(browser.get("headless", True)).lower() == "true",
            use_vision=str(browser.get("use_vision", True)).lower() == "true",
            request_interval_seconds=float(execution.get("request_interval_seconds", 3.0)),
            min_success_fields=int(agent.get("min_success_fields", 3)),
            partial_success_min_fields=int(agent.get("partial_success_min_fields", 2)),
            retry_on_failure=str(agent.get("retry_on_failure", "true")).lower() == "true",
            max_retries=int(agent.get("max_retries", 1)),
            fields=fields,
            log_level=logging_cfg.get("level", "INFO").upper(),
            log_console_output=str(logging_cfg.get("console_output", "true")).lower() == "true",
            log_file_output=str(logging_cfg.get("file_output", "true")).lower() == "true",
        )

    @staticmethod
    def _default_llm_model(config: dict[str, Any]) -> str:
        """根据可用的 API 密钥确定默认模型"""
        api_keys = config.get("api_keys", {})
        if api_keys.get("openai") or os.getenv("OPENAI_API_KEY"):
            return "openai_gpt_4o"
        if api_keys.get("browser_use") or os.getenv("BROWSER_USE_API_KEY"):
            return "bu_latest"
        return ""

    @classmethod
    def from_env(cls) -> "Settings":
        """从环境变量加载配置（保留向后兼容）"""
        return cls.from_yaml()


# 加载默认配置
settings = Settings.from_yaml()


# 向后兼容：保留旧的 OUTPUT_HEADERS 常量
OUTPUT_HEADERS = settings.OUTPUT_HEADERS
