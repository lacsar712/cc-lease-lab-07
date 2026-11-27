"""逐测清库：每支测试清空租约链路表并补规约，保证缺口/影子计数不跨测累积。

资源池与用户保持播种状态，申领用的 pool-compute/storage/net 始终可用。
"""
import pytest

from app.db import 连接

_表们 = [
    "心跳缺口影子",
    "心跳缺口",
    "操作留痕",
    "互证报告",
    "回收匣",
    "心跳",
    "租约",
]


@pytest.fixture(autouse=True)
def _清库():
    conn = 连接()
    try:
        for t in _表们:
            conn.execute(f"DELETE FROM {t}")
        conn.execute(
            "INSERT INTO 租账规(键,值) VALUES ('连续丢包上限','3') "
            "ON CONFLICT(键) DO UPDATE SET 值='3'"
        )
        conn.commit()
    finally:
        conn.close()
    yield
