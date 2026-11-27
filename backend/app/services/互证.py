from __future__ import annotations

from app.db import 连接
from app.services import 校验, 说明


def 跑一次() -> dict:
    conn = 连接()
    try:
        租约总数 = conn.execute("SELECT COUNT(*) FROM 租约").fetchone()[0]
        生效 = conn.execute(
            "SELECT COUNT(*) FROM 租约 WHERE 状态 IN ('生效中','已续约')"
        ).fetchone()[0]
        待回收 = conn.execute("SELECT COUNT(*) FROM 回收匣 WHERE 状态='待回收'").fetchone()[0]
        池已占合计 = conn.execute("SELECT COALESCE(SUM(已占),0) FROM 资源池").fetchone()[0]
        占用按租约 = conn.execute(
            "SELECT COUNT(*) FROM 租约 WHERE 状态 IN ('生效中','已续约','待生效')"
        ).fetchone()[0]
        差异 = []
        if int(池已占合计) != int(占用按租约):
            差异.append(f"池已占合计 {池已占合计} 与未回收租约数 {占用按租约} 不一致")
        禁用池租约 = conn.execute(
            """SELECT l.租约号 FROM 租约 l JOIN 资源池 p ON l.池键=p.池键
               WHERE p.启用=0 AND l.状态 IN ('生效中','已续约')"""
        ).fetchall()
        if 禁用池租约:
            差异.append(
                "禁用池仍有生效租约: " + ",".join(r["租约号"] for r in 禁用池租约)
            )
        待生效过期 = conn.execute(
            """SELECT 租约号 FROM 租约 WHERE 状态='待生效'
               AND 到期时刻 < datetime('now')"""
        ).fetchall()
        if 待生效过期:
            差异.append("待生效但已过期: " + ",".join(r["租约号"] for r in 待生效过期))

        # 心跳缺口双轨核对：正式轨与候审轨读引用面不同，影子不得算合法补偿
        超限拒延行 = conn.execute(
            "SELECT DISTINCT 租约号, 第几次拒延 FROM 心跳缺口 WHERE 处置态='超限拒延'"
        ).fetchall()
        if 超限拒延行:
            差异.append(
                "超限拒延缺口（补偿已拒·缺口已记）: "
                + ",".join(f"{r['租约号']}(第{r['第几次拒延']}次拒延)" for r in 超限拒延行)
            )
        候审缺口数 = conn.execute("SELECT COUNT(*) FROM 心跳缺口影子").fetchone()[0]
        超限拒延缺口数 = conn.execute(
            "SELECT COUNT(*) FROM 心跳缺口 WHERE 处置态='超限拒延'"
        ).fetchone()[0]
        合法补偿缺口数 = conn.execute(
            "SELECT COUNT(*) FROM 心跳缺口 WHERE 处置态='已补偿'"
        ).fetchone()[0]
        对齐 = len(差异) == 0
        结论 = "租账互证通过" if 对齐 else "租账互证发现差异"
        摘要 = "；".join(差异) if 差异 else "资源池占用与租约台账一致"
        时刻 = 校验.此刻()
        conn.execute(
            """INSERT INTO 互证报告(时刻,结论,差异摘要,租约总数,生效中数,待回收数,池已占合计,是否对齐)
               VALUES (?,?,?,?,?,?,?,?)""",
            (时刻, 结论, 摘要, 租约总数, 生效, 待回收, 池已占合计, 1 if 对齐 else 0),
        )
        报告号 = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO 操作留痕(时刻,操作,详情) VALUES (?,?,?)",
            (时刻, "跑租账互证", 摘要),
        )
        conn.commit()
        明细 = {
            "报告号": 报告号,
            "时刻": 时刻,
            "结论": 结论,
            "差异摘要": 摘要,
            "是否全部对齐": 对齐,
            "租约总数": 租约总数,
            "生效中数": 生效,
            "待回收数": 待回收,
            "池已占合计": 池已占合计,
            "按租约计占用": 占用按租约,
            "候审缺口数": int(候审缺口数),
            "超限拒延缺口数": int(超限拒延缺口数),
            "合法补偿缺口数": int(合法补偿缺口数),
        }
        return 明细
    finally:
        conn.close()