"""失败测甲：第四次丢包仍延时成功，这一支先红。

复现用夹具键连续丢包四次：前三次记心跳缺口、可补发延时；
第四次补发必须拒延时并标心跳缺口，只数心跳缺口，不涉时钟秒差。
"""
import os
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp()
os.environ["数据目录"] = _tmp
os.environ["夹具目录"] = str(Path(__file__).resolve().parents[2] / "fixtures")

import pytest

from app import seed
from app.services import 互证, 夹具, 租约, 续约, 说明
from tests.缺口夹具 import _清库  # noqa: F401  逐测清库，自动生效


def setup_module():
    seed.初始化库()
    说明.改租账规({"连续丢包上限": "3"})


def _生效租约(租约号: str) -> str:
    租约.申领(
        {
            "池键": "pool-compute",
            "租户": "gap-team-a",
            "租期分钟": 120,
            "立即生效": True,
            "租约号": 租约号,
        }
    )
    return 租约号


def _连丢四次(租约号: str):
    体 = 夹具.读取("心跳缺口夹具")
    回报 = []
    for beat in 体["心跳"]:
        回报.append(续约.发心跳({"租约号": 租约号, "模拟失败": beat["模拟失败"]}))
    return 回报


def test_连续丢包四次第四次补发必须拒延时():
    lid = _生效租约("ls-gate-a-01")
    上限 = 续约.丢包上限()
    assert 上限 == 3

    回报 = _连丢四次(lid)
    # 每次丢包回报都要带连续丢包计数，第 1～3 次未超限，第 4 次超限
    assert [r["连续丢包数"] for r in 回报] == [1, 2, 3, 4]
    assert 回报[2]["是否超限"] is False
    assert 回报[3]["是否超限"] is True

    # 计数只看心跳结果连续段，不看时钟秒差
    assert 续约.连续丢包次数(lid) == 4

    前 = 说明.租约一条(lid)
    with pytest.raises(ValueError) as ei:
        续约.补发缺口({"租约号": lid, "延长分钟": 30})
    消息 = str(ei.value)
    assert "第4次" in 消息
    assert "拒延时" in 消息

    后 = 说明.租约一条(lid)
    # 第四次补发被拒：到期一刻不得延长、续约次数不得增加
    assert 后["到期时刻"] == 前["到期时刻"]
    assert 后["续约次数"] == 前["续约次数"] == 0

    # 正式轨：四次缺口均留指纹，第四次标超限拒延；候审轨影子一行
    缺口 = {r["缺口序号"]: r for r in 说明.缺口列表(lid)}
    assert set(缺口) == {1, 2, 3, 4}
    assert 缺口[4]["处置态"] == "超限拒延"
    影子 = 说明.影子列表(lid)
    assert len(影子) == 1 and 影子[0]["缺口序号"] == 4
    assert 影子[0]["处置态"] == "候审归档"


def test_三次以内补发可以延时成功():
    lid = _生效租约("ls-gate-a-02")
    for _ in range(3):
        续约.发心跳({"租约号": lid, "模拟失败": True})
    assert 续约.连续丢包次数(lid) == 3

    前 = 说明.租约一条(lid)
    报 = 续约.补发缺口({"租约号": lid, "延长分钟": 20})
    assert 报["结果"] == "成功"
    assert "新到期时刻" in 报

    后 = 说明.租约一条(lid)
    assert 后["续约次数"] == 前["续约次数"] + 1
    assert 后["到期时刻"] != 前["到期时刻"]
    # 正式轨三行全部标已补偿，候审轨不得有影子
    assert all(r["处置态"] == "已补偿" for r in 说明.缺口列表(lid))
    assert 说明.影子列表(lid) == []

    # 缺口已补完，再补发必须拒（无缺口可补）
    with pytest.raises(ValueError):
        续约.补发缺口({"租约号": lid})


def test_成功心跳闭合缺口后计数归零():
    lid = _生效租约("ls-gate-a-03")
    续约.发心跳({"租约号": lid, "模拟失败": True})
    续约.发心跳({"租约号": lid, "模拟失败": True})
    assert 续约.连续丢包次数(lid) == 2

    续约.发心跳({"租约号": lid})  # 成功心跳闭合连续缺口段
    assert 续约.连续丢包次数(lid) == 0
    assert all(r["处置态"] == "成功闭合" for r in 说明.缺口列表(lid))

    # 闭合后重新丢包，序号从头计，第四次仍须拒延时
    for i in range(4):
        r = 续约.发心跳({"租约号": lid, "模拟失败": True})
    assert r["连续丢包数"] == 4 and r["是否超限"] is True
    with pytest.raises(ValueError) as ei:
        续约.补发缺口({"租约号": lid})
    assert "第4次" in str(ei.value) and "拒延时" in str(ei.value)
