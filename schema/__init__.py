"""schema：数据结构校验内核。

对外入口：
    Field                 一个字段的要求（类型、必填、默认值、长度、元素、嵌套字段、策略）
    validate              按模式校验一份文档，返回规整后的新文档
    Problem               一条定位到具体字段的问题（路径 + 问题类型）
    ValidationFailed      文档不合格，errors 里是全部问题
    SchemaError           内核错误的基类
    SchemaDefinitionError 模式本身写得不对
    KINDS / UNKNOWN_POLICIES / DEFAULT_UNKNOWN / CODES  常量
"""

from .core import (CODES, DEFAULT_UNKNOWN, KINDS, UNKNOWN_POLICIES, Field,
                   Problem, SchemaDefinitionError, SchemaError,
                   ValidationFailed, validate)

__all__ = [
    "CODES",
    "DEFAULT_UNKNOWN",
    "Field",
    "KINDS",
    "Problem",
    "SchemaDefinitionError",
    "SchemaError",
    "UNKNOWN_POLICIES",
    "ValidationFailed",
    "validate",
]
