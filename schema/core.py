"""数据结构校验内核。

一份模式（Field 树）说明一份文档该长什么样：哪些字段是必填的、每个字段是什么类型、
数组元素是什么、最长最短几个、嵌套对象里又有哪些字段、多余字段怎么办、缺了的字段
补什么默认值。::

    PROFILE = Field("object", fields={
        "name": Field("str", required=True),
        "age": Field("int"),
        "tags": Field("list", item=Field("str"), min_len=1, max_len=4, default=[]),
    })

    validate({"name": "ada", "age": "36"}, PROFILE)
    # -> {"name": "ada", "age": 36, "tags": []}

调用方拿到的是一份新的文档：强制过类型的值、补上的默认值、按策略处理过的多余字段
都在里面，交进来的对象一个字节都不动。

几条约定：

* 必填只看键在不在：显式写出来的 null 是「给了、但值不对」，按类型问题报，不当成
  缺失，也不会被默认值顶替；只有键真的没写才轮到默认值；
* 整数只收整数与可带正负号的十进制串，小数不截断、真值不当数字；
* 数组的长度上下限都含端点，元素的问题挂到元素自己的路径上；
* 嵌套对象逐层往下校验，问题路径用点分字段名和方括号下标拼出完整位置；
* 一次校验把问题收齐，按路径排好，同一路径上的同一个问题只留一条；
* 只要有一条问题就不返回结果（抛 ValidationFailed），不会静默补默认值；
* 多余字段按策略处理：默认拒绝（报 unknown_field），也可以 keep 或 drop；
* 补进结果的默认值先拷一份，容器里嵌套的容器也不与模式共享。

内核只在内存里算：不读文件、不读进程环境、不打印、不用随机数、不看时钟。
"""

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

#: 认识的字段类型。
KINDS = ("bool", "float", "int", "list", "object", "str")

#: 多余字段的三种策略，不写就用 DEFAULT_UNKNOWN。
UNKNOWN_POLICIES = ("reject", "keep", "drop")
DEFAULT_UNKNOWN = "reject"

#: 问题类型：字段缺失、类型不对、数组太短、数组太长、多余字段。
CODES = ("missing", "type", "too_short", "too_long", "unknown_field")


class SchemaError(Exception):
    """模式写得不对，或者文档不合格。"""


class SchemaDefinitionError(SchemaError):
    """模式本身有问题：类型不认识、数组没有元素模式、长度约束挂错了地方。"""


class Problem(object):
    """一条定位到具体字段的问题：路径 + 问题类型。"""

    __slots__ = ("path", "code")

    def __init__(self, path, code):
        self.path = path
        self.code = code

    def __eq__(self, other):
        return (isinstance(other, Problem) and self.path == other.path
                and self.code == other.code)

    def __hash__(self):
        return hash((self.path, self.code))

    def __repr__(self):
        return "Problem(%r, %r)" % (self.path, self.code)


class ValidationFailed(SchemaError, ValueError):
    """文档不合格；errors 是按路径排好、去过重的全部问题。"""

    def __init__(self, problems):
        self.errors = tuple(problems)
        summary = "；".join("%s %s" % (problem.path or "根", problem.code)
                            for problem in self.errors)
        super().__init__(summary)


class _NoDefault(object):
    """内部哨兵：这个字段没给默认值。"""

    __slots__ = ()

    def __repr__(self):
        return "<no default>"


_NO_DEFAULT = _NoDefault()


# -- 模式描述 --------------------------------------------------------------


class Field(object):
    """一个字段的要求。

    kind      "bool" / "float" / "int" / "str" / "list" / "object" 之一；
    required  这个键必须写在文档里；
    default   这个键没写时补上的值，不给就表示「没写就没有」；
    min_len   数组元素的最少个数（含端点）；
    max_len   数组元素的最多个数（含端点）；
    item      数组元素的 Field；
    fields    嵌套对象自己的字段表（字段名 -> Field）；
    unknown   多余字段策略，不给就按 DEFAULT_UNKNOWN。
    """

    __slots__ = ("kind", "required", "default", "min_len", "max_len", "item",
                 "fields", "unknown")

    def __init__(self, kind, required=False, default=_NO_DEFAULT, min_len=None,
                 max_len=None, item=None, fields=None, unknown=None):
        self.kind = kind
        self.required = bool(required)
        self.default = default
        self.min_len = min_len
        self.max_len = max_len
        self.item = item
        self.fields = fields
        self.unknown = unknown

    def __repr__(self):
        return "Field(%r%s)" % (self.kind,
                                ", required=True" if self.required else "")


def _check_definition(spec, where):
    """把一份模式从头读一遍，写错的地方直接指出来。"""
    if not isinstance(spec, Field):
        raise SchemaDefinitionError("%s 必须是一个 Field" % where)
    if spec.kind not in KINDS:
        raise SchemaDefinitionError("%s 的类型 %r 不认识" % (where, spec.kind))
    for label, bound in (("min_len", spec.min_len), ("max_len", spec.max_len)):
        if bound is None:
            continue
        if spec.kind != "list":
            raise SchemaDefinitionError("%s 的 %s 只能用在数组上" % (where, label))
        if isinstance(bound, bool) or not isinstance(bound, int) or bound < 0:
            raise SchemaDefinitionError("%s 的 %s 必须是非负整数" % (where, label))
    if (spec.min_len is not None and spec.max_len is not None
            and spec.min_len > spec.max_len):
        raise SchemaDefinitionError("%s 的长度下限比上限还大" % where)
    if spec.kind == "list":
        if spec.item is None:
            raise SchemaDefinitionError("%s 是数组，必须给出元素模式" % where)
        _check_definition(spec.item, where + "[]")
    if spec.kind == "object":
        if not isinstance(spec.fields, dict) or not spec.fields:
            raise SchemaDefinitionError("%s 是对象，必须给出字段表" % where)
        for name, child in spec.fields.items():
            if not isinstance(name, str) or not name:
                raise SchemaDefinitionError("%s 的字段名必须是非空文本" % where)
            _check_definition(child, _join(where, name))
    if spec.unknown is not None and spec.unknown not in UNKNOWN_POLICIES:
        raise SchemaDefinitionError("%s 的多余字段策略 %r 不认识" % (where, spec.unknown))
    return spec


# -- 小工具 ----------------------------------------------------------------


def _join(path, name):
    """把字段名接到路径后面。"""
    return name if not path else "%s.%s" % (path, name)


def _clone(value):
    """拷一份容器：默认值与 keep 下来的原值都不跟调用方共享。"""
    if isinstance(value, dict):
        return {key: _clone(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clone(item) for item in value]
    return value


def _report(problems, path, code):
    """记下一条问题。"""
    problems.append(Problem(path, code))


# -- 逐字段校验 ------------------------------------------------------------


def _is_present(document, name):
    """这个字段是不是真的写在文档里了。"""
    return name in document


def _unknown_policy(spec):
    """对象自己没写策略时按内核默认。"""
    return spec.unknown if spec.unknown is not None else DEFAULT_UNKNOWN


def _normalize(document, spec, path, problems):
    """校验一个值，返回规整后的值；不合格的地方记成问题。"""
    if spec.kind == "object":
        return _normalize_object(document, spec, path, problems)
    if spec.kind == "list":
        return _normalize_list(document, spec, path, problems)
    return _normalize_scalar(document, spec, path, problems)


def _normalize_object(document, spec, path, problems):
    """逐字段校验一个对象，顺带处理多余字段。"""
    if not isinstance(document, dict):
        _report(problems, path, "type")
        return None
    policy = _unknown_policy(spec)
    normalized = {}
    for name in sorted(document):
        if name in spec.fields:
            continue
        if policy == "keep":
            normalized[name] = _clone(document[name])
        elif policy == "drop":
            continue
        else:
            _report(problems, _join(path, name), "unknown_field")
    for name, field in spec.fields.items():
        child_path = _join(path, name)
        if not _is_present(document, name):
            if field.required:
                _report(problems, child_path, "missing")
            elif field.default is not _NO_DEFAULT:
                normalized[name] = _clone(field.default)
            continue
        value = _normalize(document[name], field, child_path, problems)
        if value is not None:
            normalized[name] = value
    return normalized


def _normalize_list(document, spec, path, problems):
    """校验一个数组：长度上下限与每一个元素。"""
    if not isinstance(document, list):
        _report(problems, path, "type")
        return None
    if spec.min_len is not None and len(document) < spec.min_len:
        _report(problems, path, "too_short")
    if spec.max_len is not None and len(document) > spec.max_len:
        _report(problems, path, "too_long")
    items = []
    for index, item in enumerate(document):
        items.append(_normalize(item, spec.item,
                                "%s[%d]" % (path, index), problems))
    return items


def _coerce_int(value):
    """整数只认整数与可带正负号的十进制串，别的都收不了。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value
        sign = 1
        if text[:1] in ("+", "-"):
            if text[0] == "-":
                sign = -1
            text = text[1:]
        if text and all(char in "0123456789" for char in text):
            return sign * int(text)
    return None


def _coerce_float(value):
    """浮点数收整数、浮点数与十进制串。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _normalize_scalar(document, spec, path, problems):
    """校验一个标量，能强制的强制，不能强制的报类型问题。"""
    if spec.kind == "int":
        value = _coerce_int(document)
    elif spec.kind == "float":
        value = _coerce_float(document)
    elif spec.kind == "bool":
        value = document if isinstance(document, bool) else None
    else:
        value = document if isinstance(document, str) else None
    if value is None:
        _report(problems, path, "type")
        return None
    return value


def _finalize(problems):
    """把问题按路径排好，同一处的同一个问题只留一条。"""
    unique = []
    seen = set()
    for problem in sorted(problems, key=lambda item: (item.path, item.code)):
        key = (problem.path, problem.code)
        if key in seen:
            continue
        seen.add(key)
        unique.append(problem)
    return tuple(unique)


# -- 对外入口 --------------------------------------------------------------


def validate(document, schema):
    """按模式校验一份文档，返回规整后的新文档。

    全部通过对返回新文档：强制过类型的值、补上的默认值、按策略处理过的多余字段
    都在里面，交进来的对象不被改动。只要有一条问题，就抛 ValidationFailed，
    errors 里是按路径排好、同一个问题只留一条的完整清单。
    """
    _check_definition(schema, "根模式")
    problems = []
    value = _normalize(document, schema, "", problems)
    if problems:
        raise ValidationFailed(_finalize(problems))
    return value
