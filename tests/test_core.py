"""数据结构校验内核的行为测试。

每个期望都写成平平的结果：一份规整后的文档，或者一串 (路径, 问题类型)。
从项目根跑：

    python3 -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from schema.core import (DEFAULT_UNKNOWN, Field, SchemaDefinitionError,
                         ValidationFailed, validate)


def outcome(document, schema):
    """跑一次校验：通过就给规整后的文档，不通过就给问题清单。"""
    try:
        return validate(document, schema)
    except ValidationFailed as failed:
        return [(problem.path, problem.code) for problem in failed.errors]


def problems(document, schema):
    """跑一次校验，只取问题清单；通过了就是 None。"""
    result = outcome(document, schema)
    return result if isinstance(result, list) else None


class RequiredFieldTest(unittest.TestCase):
    """必填与可选：什么算写过了，什么算没写。"""

    def test_a_document_that_already_fits_comes_back_the_same(self):
        schema = Field("object", fields={
            "name": Field("str", required=True),
            "age": Field("int"),
            "tags": Field("list", item=Field("str"), min_len=1, max_len=3,
                          default=["new"]),
        })
        document = {"name": "ada", "age": 36, "tags": ["math", "code"]}

        self.assertEqual(outcome(document, schema), document)
        self.assertEqual(document, {"name": "ada", "age": 36,
                                    "tags": ["math", "code"]})
        self.assertEqual(outcome(document, schema), document)

    def test_every_missing_required_field_is_reported_once(self):
        schema = Field("object", fields={
            "name": Field("str", required=True),
            "age": Field("int", required=True),
            "note": Field("str"),
        })

        self.assertEqual(problems({"note": "hi"}, schema),
                         [("age", "missing"), ("name", "missing")])
        self.assertEqual(problems({"name": "ada", "age": 36, "note": "hi"},
                                  schema), None)

    def test_a_written_null_is_a_type_problem_not_a_missing_field(self):
        schema = Field("object", fields={
            "name": Field("str", required=True),
            "tags": Field("list", item=Field("str"), default=["new"]),
            "note": Field("str"),
        })

        self.assertEqual(problems({"name": None, "tags": None, "note": None},
                                  schema),
                         [("name", "type"), ("note", "type"), ("tags", "type")])
        self.assertEqual(problems({"name": None}, schema), [("name", "type")])
        self.assertEqual(problems({"name": "ada", "note": None}, schema),
                         [("note", "type")])
        with self.assertRaises(ValidationFailed):
            validate({"name": "ada", "tags": None}, schema)


class TypeCoercionTest(unittest.TestCase):
    """类型强制与拒绝：能收的收下，不能收的报类型问题。"""

    def test_number_text_is_coerced_with_its_sign(self):
        schema = Field("object", fields={
            "offset": Field("int", required=True),
            "limit": Field("int"),
            "ratio": Field("float"),
        })

        self.assertEqual(outcome({"offset": "-7", "limit": "+3"}, schema),
                         {"offset": -7, "limit": 3})
        self.assertEqual(outcome({"offset": "12", "ratio": "1.5"}, schema),
                         {"offset": 12, "ratio": 1.5})
        self.assertEqual(outcome({"offset": -7, "limit": 3, "ratio": 1.5},
                                 schema),
                         {"offset": -7, "limit": 3, "ratio": 1.5})
        for text in ("1.5", "seven", "", "--7", "7 "):
            with self.subTest(text=text):
                self.assertEqual(problems({"offset": text}, schema),
                                 [("offset", "type")])
        for other in (3.7, True, ["7"]):
            with self.subTest(value=other):
                self.assertEqual(problems({"offset": other}, schema),
                                 [("offset", "type")])


class ArrayConstraintTest(unittest.TestCase):
    """数组的长度约束与元素校验。"""

    def test_length_bounds_include_their_endpoints(self):
        schema = Field("object", fields={
            "tags": Field("list", item=Field("str"), min_len=2, max_len=4),
        })

        self.assertEqual(outcome({"tags": ["a", "b"]}, schema),
                         {"tags": ["a", "b"]})
        self.assertEqual(outcome({"tags": ["a", "b", "c", "d"]}, schema),
                         {"tags": ["a", "b", "c", "d"]})
        self.assertEqual(problems({"tags": ["a"]}, schema),
                         [("tags", "too_short")])
        self.assertEqual(problems({"tags": ["a", "b", "c", "d", "e"]}, schema),
                         [("tags", "too_long")])
        self.assertEqual(problems({"tags": []}, schema),
                         [("tags", "too_short")])

    def test_element_and_nested_problems_point_at_the_exact_field(self):
        schema = Field("object", fields={
            "tags": Field("list", item=Field("str")),
            "meta": Field("object", fields={
                "tags": Field("list", item=Field("str"), min_len=1),
            }),
        })

        self.assertEqual(outcome({"tags": ["a"], "meta": {"tags": ["x"]}},
                                 schema),
                         {"tags": ["a"], "meta": {"tags": ["x"]}})
        self.assertEqual(problems({"tags": ["a", 7], "meta": {"tags": []}},
                                  schema),
                         [("meta.tags", "too_short"), ("tags[1]", "type")])
        self.assertEqual(problems({"tags": ["a"], "meta": {"tags": [1]}},
                                  schema),
                         [("meta.tags[0]", "type")])


class UnknownFieldTest(unittest.TestCase):
    """多余字段的三个策略。"""

    def test_unknown_fields_follow_the_declared_policy(self):
        def with_policy(policy):
            extra = {} if policy is None else {"unknown": policy}
            return Field("object", fields={"name": Field("str", required=True)},
                         **extra)

        document = {"name": "ada", "extra": 1}
        self.assertEqual(DEFAULT_UNKNOWN, "reject")
        self.assertEqual(problems(document, with_policy(None)),
                         [("extra", "unknown_field")])
        self.assertEqual(problems(document, with_policy("reject")),
                         [("extra", "unknown_field")])
        self.assertEqual(outcome(document, with_policy("drop")), {"name": "ada"})
        self.assertEqual(outcome(document, with_policy("keep")), document)
        self.assertEqual(outcome({"name": "ada"}, with_policy("reject")),
                         {"name": "ada"})

        kept = outcome({"name": "ada", "extra": {"deep": [1]}},
                       with_policy("keep"))
        self.assertEqual(kept, {"name": "ada", "extra": {"deep": [1]}})
        kept["extra"]["deep"].append(2)
        self.assertEqual(outcome({"name": "ada", "extra": {"deep": [1]}},
                                 with_policy("keep")),
                         {"name": "ada", "extra": {"deep": [1]}})


class NestedObjectTest(unittest.TestCase):
    """嵌套对象逐层往下校验。"""

    def test_nested_objects_are_checked_level_by_level(self):
        schema = Field("object", fields={
            "user": Field("object", unknown="drop", fields={
                "name": Field("str", required=True),
                "contact": Field("object", default={"mail": "none"}, fields={
                    "mail": Field("str", required=True),
                }),
            }),
        })

        self.assertEqual(outcome({"user": {"name": "ada",
                                           "contact": {"mail": "m"},
                                           "junk": 1}}, schema),
                         {"user": {"name": "ada", "contact": {"mail": "m"}}})
        self.assertEqual(outcome({"user": {"name": "ada"}}, schema),
                         {"user": {"name": "ada", "contact": {"mail": "none"}}})
        self.assertEqual(problems({"user": {"contact": {"mail": 7}}}, schema),
                         [("user.contact.mail", "type"),
                          ("user.name", "missing")])
        self.assertEqual(problems({"user": {"name": "ada",
                                           "contact": {"mail": "m", "junk": 2}}},
                                  schema),
                         [("user.contact.junk", "unknown_field")])


class DefaultValueTest(unittest.TestCase):
    """默认值只补没写的键，而且补进去的不是模式里那一份。"""

    def test_defaults_fill_absent_keys_without_being_shared(self):
        schema = Field("object", fields={
            "tags": Field("list", item=Field("str"), default=["new"]),
            "rows": Field("list", item=Field("list", item=Field("int")),
                          default=[[1]]),
        })

        first = outcome({}, schema)
        self.assertEqual(first, {"tags": ["new"], "rows": [[1]]})
        first["tags"].append("more")
        first["rows"][0].append(2)
        self.assertEqual(outcome({}, schema), {"tags": ["new"], "rows": [[1]]})
        self.assertEqual(outcome({"tags": ["old"]}, schema),
                         {"tags": ["old"], "rows": [[1]]})
        self.assertEqual(outcome({"tags": []}, schema),
                         {"tags": [], "rows": [[1]]})


class GuardTest(unittest.TestCase):
    """调用方的东西不被改动，坏模式不许当成好模式用。"""

    def test_document_hygiene_and_broken_schemas(self):
        schema = Field("object", fields={
            "name": Field("str", required=True),
            "tags": Field("list", item=Field("str"), default=[]),
            "user": Field("object", fields={"mail": Field("str", required=True)}),
        })
        document = {"name": "ada", "tags": ["math"], "user": {"mail": "m"}}

        self.assertEqual(outcome(document, schema), document)
        self.assertEqual(document, {"name": "ada", "tags": ["math"],
                                    "user": {"mail": "m"}})
        self.assertEqual(outcome({}, Field("object", fields={"note": Field("str")})),
                         {})

        broken = (
            Field("object", fields={"x": Field("text")}),
            Field("object", fields={"x": Field("list")}),
            Field("object", fields={"x": Field("object")}),
            Field("object", fields={"x": Field("list", item=Field("str"),
                                               min_len=3, max_len=1)}),
            Field("object", fields={"x": Field("int", min_len=1)}),
            Field("object", fields={"x": Field("str", unknown="sort")}),
        )
        for spec in broken:
            with self.subTest(schema=repr(spec)):
                with self.assertRaises(SchemaDefinitionError):
                    validate({}, spec)

        self.assertEqual(problems([1, 2], Field("object", fields={"x": Field("str")})),
                         [("", "type")])


if __name__ == "__main__":
    unittest.main()
