接口加了防重放窗口，攻击者把序号跳过一大段再回填，窗口位图直接乱套：位图掩码在位移超过位宽时不钳制，掩码变成全一；窗口整体移动只做按位右移而没有清除移出位，旧序号仍被当作已见过；窗口回退移动使用算术右移，最高位被符号扩展污染；重复标记同一序号时翻转该位而不是置一，第二次标记反而把已见位清掉；窗口之外的旧序号被判为未见过，旧包可以重放；窗口跳跃推进时没有把中间位清零，中间序号被误判为已使用；边界序号等于最大序号减窗口大小加一，被排除在窗口之外，合法包被拒绝；初始位图没有置零，最前面的几个序号被误判为已见过；校验只检查最大序号，不检查位图长度与窗口大小是否一致；批量处理复用同一个窗口状态，第二个连接命中第一个连接的位图。replay/window.py 是核心，tests/test_window.py 15个红。要修的是：按上面的顺序把 10 个缺陷逐个修掉。

## 运行方式

在仓库根目录执行：

```bash
python -m pytest tests -q
```

修复前预期输出为 `15 failed`，15 条失败全部是 `NotImplementedError`；把 `src/replay/window.py` 的 8 个桩按正确语义实现后，预期输出为 `15 passed`。

## 目录布局与导入路径

```text
sec-replay-window/
  README.md
  pyproject.toml
  src/
    replay/
      __init__.py
      window.py
  tests/
    test_window.py
```

`pyproject.toml` 的 `[tool.pytest.ini_options]` 中写有 `pythonpath = ["src"]`，因此测试可以直接 `from replay.window import ...`，不需要安装包，也不需要 `pip install -e .`。`src/replay/window.py` 是唯一实现文件，只有 8 个公开函数，没有额外的私有辅助函数；`tests/test_window.py` 是只读验收文件。

## 状态字段

窗口状态是普通字典，所有函数都是纯函数：返回新的状态字典，绝不修改传入的状态。

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| size | int | 窗口宽度（槽位数量），至少为 1 |
| max_seq | int | 已经接受的最大序号；0 表示还没有接受过任何序号 |
| bitmap | int | 位图；位 i 为 1 表示序号 max_seq - i 已被使用，位 0 对应 max_seq |
| accepted | int | 累计接受次数 |
| rejected | int | 累计拒绝次数 |

## 函数契约

| 函数 | 契约 |
| --- | --- |
| init_window(size) | 返回全零位图、max_seq 为 0 的新窗口 |
| mask_for(size, shift) | 返回最低 shift 位的掩码；shift 小于 0 时按 0，超过 size 时按 size 钳制 |
| shift_window(state, delta) | 窗口整体移动 delta 格；前进时移出窗口的高位清零，回退时超出新 max_seq 的位丢弃，位图不得为负 |
| mark(state, seq) | 在窗口内把 seq 对应的位置一；同一序号重复标记结果不变 |
| seen(state, seq) | 返回 seq 是否已使用；seq 小于窗口下界时视为已使用，返回 True |
| accept(state, seq) | 返回 accepted 与 state 两个键；窗口内重复序号拒绝，窗口外旧序号拒绝，合法新序号接受并推进窗口 |
| validate_window(state, size) | 返回问题码列表，合法状态返回空列表 |
| window_batch(events, size) | events 是连接标识与序号的二元组序列；每个连接使用独立窗口，返回连接标识到状态的字典 |

## 关键语义

窗口覆盖闭区间 `[max_seq - size + 1, max_seq]`，两个端点都在窗口内。序号大于 max_seq 时窗口跳跃推进：跳过的中间槽位必须为 0，一次跳过不少于窗口宽度的距离后位图只保留新序号对应的位 0。序号落在窗口内且对应位为 0 时接受并置位；对应位为 1 时按重复包拒绝。序号小于窗口下界时，`seen` 返回 True 且 `accept` 一律拒绝，旧包不能重放。`mark` 只做幂等的置位，不推进窗口。`window_batch` 不得在连接之间复用状态。

`validate_window` 的问题码固定为三个字符串：`bitmap_size_mismatch` 表示位图有效位数大于窗口宽度，`max_seq_negative` 表示最大序号为负，`mask_overflow` 表示整窗掩码超出位宽。

## 字段表

| 项 | 值 |
| --- | --- |
| 大类 | 安全 |
| 细分方向 | 漏洞检测与攻防 |
| 任务类型 | Bugfix |
| 运行环境 | Python 3, pytest |
| 外部依赖 | 无外部依赖 |

## 约束

`tests/test_window.py` 不可修改，评分以这 15 条测试为准；只允许修改 `src/replay/window.py`。题面中的 10 个缺陷按 1 到 10 编号，依次对应测试文件里的前 10 条缺陷测试；最后 5 条是交叉校验：首次标记后可判定为已见、窗口内更大的新序号被接受、超出窗口下界的旧序号被拒、跳跃后中间序号未被标记、两批独立处理与逐条单独处理一致。不要用修改测试、跳过测试、放宽断言的方式通过。

## 字段表

| 字段 | 取值 |
| --- | --- |
| 所属领域 | 安全 |
| 子方向 | 漏洞检测与攻防 |
| 任务类型 | Bugfix |
| 语言/框架 | Python 3, pytest |
| 环境可复现等级 | 无外部依赖 |

