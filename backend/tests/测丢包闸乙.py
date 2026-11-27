"""失败测乙：互证把超限影子误标成合法补偿，这一支再红。

候审轨（心跳缺口影子）只作只读归档，互证必须把超限拒延缺口
单列为差异，绝不能把候审影子算成合法补偿。该红只能在互证服务消。
"""
import os
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp()
os.environ["数据目录"] = _tmp
os.environ["夹具目录"] = str(Path(__file__).resolve().parents[2] / "fixtures")

import pytest

from app import seed
from app.services import 互证, 租约, 续约, 说明
from tests.缺口夹具 import _清库  # noqa: F401  逐测清库，自动生效


def setup_module():
    seed.初始化库()
    说明.改租账规({"连续丢包上限": "3"})


def _生效租约(租约号: str, 租户: str) -> str:
    租约.申领(
        {
            "池键": "pool-storage",
            "租户": 租户,
            "租期分钟": 120,
            "立即生效": True,
            "租约号": 租约号,
        }
    )
    return 租约号


def test_互证单列超限影子不得算合法补偿():
    超限号 = _生效租约("ls-gate-b-01", "gap-team-b1")
    for _ in range(4):
        续约.发心跳({"租约号": 超限号, "模拟失败": True})
    with pytest.raises(ValueError) as ei:
        续约.补发缺口({"租约号": 超限号})
    assert "拒延时" in str(ei.value)

    合法号 = _生效租约("ls-gate-b-02", "gap-team-b2")
    for _ in range(3):
        续约.发心跳({"租约号": 合法号, "模拟失败": True})
    续约.补发缺口({"租约号": 合法号, "延长分钟": 20})

    报告 = 互证.跑一次()

    # 候审轨与正式轨在互证明细里必须分列，读引用面不同
    assert 报告["候审缺口数"] == 1
    assert 报告["超限拒延缺口数"] == 1
    assert 报告["合法补偿缺口数"] == 3

    # 超限租约进差异，合法补偿租约不进差异；影子不得被认成合法补偿
    摘要 = 报告["差异摘要"]
    assert 超限号 in 摘要
    assert "超限" in 摘要 and "拒延" in 摘要
    assert 合法号 not in 摘要
    assert 报告["是否全部对齐"] is False

    # 影子轨自身口径：候审归档一行，且没有任何一行处置态被改成已补偿
    影子 = 说明.影子列表(超限号)
    assert len(影子) == 1
    assert 影子[0]["处置态"] == "候审归档"
    正式 = 说明.缺口列表(超限号)
    assert all(r["处置态"] != "已补偿" for r in 正式)
    合法缺口 = 说明.缺口列表(合法号)
    assert all(r["处置态"] == "已补偿" for r in 合法缺口)


def test_无超限缺口时互证不凭空报差异():
    lid = _生效租约("ls-gate-b-03", "gap-team-b3")
    for _ in range(2):
        续约.发心跳({"租约号": lid, "模拟失败": True})
    续约.补发缺口({"租约号": lid, "延长分钟": 10})

    报告 = 互证.跑一次()
    assert 报告["候审缺口数"] == 0
    assert 报告["超限拒延缺口数"] == 0
    assert "超限" not in 报告["差异摘要"]
