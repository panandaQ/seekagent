from __future__ import annotations

import re
from pydantic import BaseModel, Field, field_validator
from typing import Any


class ExpertInfo(BaseModel):
    """专家信息模型 - 支持动态字段"""
    name: str = Field(description="专家姓名")
    biography: str | None = Field(default=None, description="个人简介")
    affiliation: str | None = Field(default=None, description="所属单位")
    email: str | None = Field(default=None, description="电子邮箱")
    phone: str | None = Field(default=None, description="联系电话")
    source_urls: list[str] = Field(default_factory=list, description="信息来源URL列表")
    status: str = Field(default="失败", description="提取状态：成功/失败")
    notes: str | None = Field(default=None, description="备注")

    # 动态字段存储
    extra_fields: dict[str, Any] = Field(default_factory=dict, description="额外的动态字段")

    @field_validator("source_urls", mode="before")
    @classmethod
    def _coerce_source_urls(cls, value: Any) -> list[str]:
        if value is None:
            return []

        def _split_text(text: str) -> list[str]:
            parts = re.split(r"[,，;；\n\r\t\s]+", text)
            return [p.strip() for p in parts if p and p.strip()]

        if isinstance(value, str):
            return _split_text(value)

        if isinstance(value, (tuple, set)):
            value = list(value)

        if isinstance(value, list):
            urls: list[str] = []
            for item in value:
                if item is None:
                    continue
                if isinstance(item, str):
                    urls.extend(_split_text(item))
                else:
                    text = str(item).strip()
                    if text:
                        urls.append(text)
            return urls

        text = str(value).strip()
        return [text] if text else []

    @field_validator("email", "phone", mode="before")
    @classmethod
    def _coerce_contact_fields(cls, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            return text or None
        if isinstance(value, (list, tuple, set)):
            normalized = [str(item).strip() for item in value if item is not None and str(item).strip()]
            return ",".join(normalized) if normalized else None
        text = str(value).strip()
        return text or None

    def __getitem__(self, key: str) -> Any:
        """支持字典式访问，兼容动态字段"""
        if hasattr(self, key):
            return getattr(self, key)
        return self.extra_fields.get(key)

    def __setitem__(self, key: str, value: Any) -> None:
        """支持字典式设置，兼容动态字段"""
        if hasattr(self, key):
            setattr(self, key, value)
        else:
            self.extra_fields[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """字典式 get 方法"""
        try:
            return self[key]
        except (AttributeError, KeyError):
            return default

    def filled_fields_count(self, config_fields: list[str]) -> int:
        """计算已填充的字段数量（基于配置的字段列表）"""
        count = 0
        for field_name in config_fields:
            value = self[field_name]
            if value not in (None, ""):
                count += 1
        if self.source_urls:
            count += 1
        return count

    def missing_critical_fields(self, config_fields: list[str]) -> list[str]:
        """检查关键字段是否缺失"""
        critical_fields = ["email", "phone"]
        missing = []
        for field in critical_fields:
            if field in config_fields:
                value = self[field]
                if not value or value in ("", None):
                    missing.append(field)
        return missing

    def normalized(self) -> "ExpertInfo":
        """规范化数据"""
        result = self.model_copy()
        # 清理字符串字段
        for field_name in ExpertInfo.model_fields:
            if field_name == "source_urls":
                result.source_urls = [u.strip() for u in self.source_urls if u and u.strip()]
                continue
            if field_name == "extra_fields":
                continue
            value = getattr(result, field_name, None)
            if isinstance(value, str):
                setattr(result, field_name, value.strip())
        return result

    def to_dict(self, field_order: list[str]) -> dict[str, Any]:
        """按指定字段顺序转换为字典"""
        result = {}
        for key in field_order:
            result[key] = self[key]
        # 添加固定字段
        result["source_urls"] = ", ".join(self.source_urls) if self.source_urls else ""
        result["status"] = self.status
        result["notes"] = self.notes or ""
        return result
