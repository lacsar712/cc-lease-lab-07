"""争用失败测丙：两名操作员同时补发缺口心跳，不加锁就会双成功、缺口计数互盖。

双会话抢补发，必须一成一拒：续约次数只加一、正式轨只补一次、
候审轨不产生影子。超限场景两侧同时补发则两侧皆拒，影子仍只有一行。
"""
import os
import tempfile
import threading
from pathlib import Path

_tmp = tempfile.mkdtemp()
os.environ["数据目录"] = _tmp
os.environ["夹具目录"] = str(Path(__file__).resolve().parents[2] / "fixtures")

from app import seed
from app.services import 租约, 续约, 说明
from tests.缺口夹具 import _清库  # noqa: F401  逐测清库，自动生效


def setup_module():
    seed.初始化库()
    说明.改租账规({"连续丢包上限": "3"})


def _生效租约(租约号: str, 租户: str) -> str:
    租约.申领(
        {
            "池键": "pool-net",
            "租户": 租户,
            "租期分钟": 120,
            "立即生效": True,
            "租约号": 租约号,
        }
    )
    return 租约号


def _双发(租约号: str):
    结果 = []
    栅栏 = threading.Barrier(2)

    def 操作员(编号):
        栅栏.wait()
        try:
            r = 续约.补发缺口({"租约号": 租约号, "延长分钟": 30})
            结果.append(("成功", 编号, r))
        except ValueError as e:
            结果.append(("拒绝", 编号, str(e)))

    t1 = threading.Thread(target=操作员, args=(1,))
    t2 = threading.Thread(target=操作员, args=(2,))
    t1.start()
    t2.start()
    t1.join(timeout=30)
    t2.join(timeout=30)
    assert not t1.is_alive() and not t2.is_alive(), "双发线程挂死"
    return 结果


def test_双会话同时补发只允许一成一拒():
    lid = _生效租约("ls-gate-c-01", "gap-team-c1")
    for _ in range(3):
        续约.发心跳({"租约号": lid, "模拟失败": True})

    结果 = _双发(lid)
    assert len(结果) == 2
    成功方 = [x for x in 结果 if x[0] == "成功"]
    拒绝方 = [x for x in 结果 if x[0] == "拒绝"]
    assert len(成功方) == 1
    assert len(拒绝方) == 1
    assert "已补偿" in 拒绝方[0][2] or "无缺口" in 拒绝方[0][2]

    后 = 说明.租约一条(lid)
    assert 后["续约次数"] == 1  # 不加锁双成功会变成 2
    补发行 = [h for h in 说明.心跳列表(lid) if h["结果"] == "成功" and "缺口补发" in h["说明"]]
    assert len(补发行) == 1

    缺口 = 说明.缺口列表(lid)
    assert len(缺口) == 3
    assert all(r["处置态"] == "已补偿" for r in 缺口)
    # 未超限，候审轨一行影子都不许有
    assert 说明.影子列表(lid) == []


def test_超限后双会话同时补发两侧皆拒且影子只一行():
    lid = _生效租约("ls-gate-c-02", "gap-team-c2")
    for _ in range(4):
        续约.发心跳({"租约号": lid, "模拟失败": True})

    结果 = _双发(lid)
    assert len(结果) == 2
    assert all(x[0] == "拒绝" for x in 结果)
    assert all("拒延时" in x[2] for x in 结果)

    后 = 说明.租约一条(lid)
    assert 后["续约次数"] == 0
    影子 = 说明.影子列表(lid)
    assert len(影子) == 1  # 指纹 UPSERT，并发不得双写
    assert 影子[0]["处置态"] == "候审归档"
    缺口 = 说明.缺口列表(lid)
    assert 缺口[-1]["处置态"] == "超限拒延"
