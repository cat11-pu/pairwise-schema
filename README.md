# schema

一个只依赖 Python 标准库、纯内存的数据结构校验内核：按一份模式树检查一份文档，把类型
强制、必填与可选、数组元素与长度、嵌套对象、多余字段策略、默认值补齐一次做完，问题按
路径汇总成一份清单。内核不读写文件、不联网、不看时钟、不用随机数，也不碰进程环境。

- 模式是一棵 `Field` 树。字段类型有 `bool`、`float`、`int`、`str`、`list`、`object`；
  `required` 表示键必须写在文档里，`default` 表示键没写时补什么。
- 类型强制：整数收整数与可带正负号的十进制串，浮点数收整数、浮点数与十进制串，文本与
  真假值只收本来的类型；收不了的一律按类型问题报，不截断、不硬转。
- 数组：`min_len` 与 `max_len` 都含端点；`item` 是元素的模式，元素的问题挂到
  `字段[下标]` 上。
- 嵌套对象：`fields` 里可以再套 `fields`，逐层往下校验，问题路径用点分字段名与方括号
  下标拼出它在文档里的完整位置。
- 多余字段：`unknown` 取 `"reject"`（默认，报 `unknown_field`）、`"keep"`（原样留下）、
  `"drop"`（从结果里剥掉）。
- 默认值：只有键真的没写才补；补进去的是拷贝，容器里嵌套的容器也不与模式共享。
- 问题：`validate` 一次收齐，按路径排好，同一路径上的同一个问题只留一条；只要有一条
  问题就抛 `ValidationFailed`，不返回半成品，也不静默补默认值。

## 目录

- `schema/core.py`：模式描述与校验内核
- `tests/test_core.py`：内核的行为测试

## 怎么跑测试

在项目根目录执行：

    python3 -m unittest discover -s tests -v

Windows 上把 `python3` 换成你的解释器路径，例如：

    C:/Users/<你>/AppData/Local/Programs/Python/Python313/python.exe -m unittest discover -s tests -v
