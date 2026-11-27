from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.db import 连接
from app.services import 校验, 说明

# 处置态口径
态_缺口已记 = "缺口已记"
态_已补偿 = "已补偿"
态_成功闭合 = "成功闭合"
态_超限拒延 = "超限拒延"
态_候审归档 = "候审归档"


def _留痕(conn, 操作, 租约号, 详情=""):
    conn.execute(
        "INSERT INTO 操作留痕(时刻,操作,租约号,详情) VALUES (?,?,?,?)",
        (校验.此刻(), 操作, 租约号, 详情),
    )


def _默认延长分钟() -> int:
    规 = 说明.租账规()
    try:
        return max(5, int(规.get("默认租期分钟", "120")))
    except ValueError:
        return 120


def 丢包上限() -> int:
    """连续丢包上限，写在租账规；缺省 3，即第四次必须拒延时。"""
    规 = 说明.租账规()
    try:
        return max(1, int(规.get("连续丢包上限", "3")))
    except ValueError:
        return 3


def 连续丢包次数(租约号: str, conn=None) -> int:
    """只数心跳结果连续段的缺口次数（自联查），不涉时钟秒差。"""
    自带 = conn is not None
    if not 自带:
        conn = 连接()
    try:
        # 联查路径：按插入顺序（rowid 单调）回溯，时刻仅展示不参与判定，
        # 故同秒多跳也不会乱序——只数心跳缺口，不涉时钟秒差。
        rows = conn.execute(
            "SELECT 结果 FROM 心跳 WHERE 租约号=? ORDER BY rowid DESC",
            (租约号,),
        ).fetchall()
        if not rows or rows[0]["结果"] == "成功":
            return 0
        n = 0
        for r in rows:
            if r["结果"] == "成功":
                break
            n += 1
        return n
    finally:
        if not 自带:
            conn.close()


def _下一缺口序号(conn, 租约号: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(缺口序号),0)+1 AS n FROM 心跳缺口 WHERE 租约号=?",
        (租约号,),
    ).fetchone()
    return int(row["n"])


def _写候审影子(conn, 租约号: str, 序号: int, 心跳号: str, 时刻: str, 第几次: int):
    """候审轨：指纹 UPSERT，并发补发也只留一行；放行判定不读本表。"""
    conn.execute(
        """INSERT INTO 心跳缺口影子(租约号,缺口序号,心跳号,时刻,处置态,第几次拒延,时刻归档)
           VALUES (?,?,?,?,?,?,?)
           ON CONFLICT(租约号,缺口序号) DO UPDATE SET
             第几次拒延=excluded.第几次拒延, 时刻归档=excluded.时刻归档""",
        (租约号, 序号, 心跳号, 时刻, 态_候审归档, 第几次, 校验.此刻()),
    )


def 发心跳(body: dict) -> dict:
    租约号 = 校验.租约号(body.get("租约号"))
    模拟失败 = bool(body.get("模拟失败"))
    conn = 连接()
    try:
        row = conn.execute("SELECT * FROM 租约 WHERE 租约号=?", (租约号,)).fetchone()
        if not row:
            raise ValueError("无此租约")
        if row["状态"] not in ("生效中", "已续约", "待生效"):
            raise ValueError("当前状态不可心跳")
        if row["状态"] == "待生效":
            raise ValueError("请先激活租约再发心跳")
        心跳号 = f"hb-{uuid.uuid4().hex[:8]}"
        结果 = "失败" if 模拟失败 else "成功"
        延迟 = int(body.get("延迟毫秒") or 35)
        说明文 = str(body.get("说明") or "页面手动心跳")
        时刻 = 校验.此刻()
        conn.execute(
            """INSERT INTO 心跳(心跳号,租约号,时刻,结果,延迟毫秒,说明) VALUES (?,?,?,?,?,?)""",
            (心跳号, 租约号, 时刻, 结果, 延迟, 说明文),
        )
        回报 = {"心跳号": 心跳号, "租约号": 租约号, "结果": 结果}

        if 结果 == "成功":
            # 成功心跳闭合当前连续缺口段：放行轨快照口，仅处理缺口已记行
            conn.execute(
                """UPDATE 心跳缺口 SET 处置态=?, 补偿时=?
                   WHERE 租约号=? AND 处置态=?""",
                (态_成功闭合, 时刻, 租约号, 态_缺口已记),
            )
            延长 = int(body.get("延长分钟") or _默认延长分钟() // 4)
            延长 = 校验.正整数("延长分钟", 延长, 下限=1, 上限=24 * 60)
            新到期 = datetime.now(timezone.utc) + timedelta(minutes=延长)
            iso = 新到期.strftime("%Y-%m-%dT%H:%M:%SZ")
            conn.execute(
                """UPDATE 租约 SET 状态='已续约', 到期时刻=?, 续约次数=续约次数+1, 更新时=?
                   WHERE 租约号=?""",
                (iso, 时刻, 租约号),
            )
            回报["新到期时刻"] = iso
            回报["状态"] = "已续约"
            回报["连续丢包数"] = 0
            回报["是否超限"] = False
            _留痕(conn, "心跳续约", 租约号, "成功·缺口段闭合")
        else:
            # 丢包：正式轨快照落指纹；连续段计数判定是否到第四次
            连续数 = 连续丢包次数(租约号, conn)
            上限 = 丢包上限()
            超限 = 连续数 > 上限
            序号 = _下一缺口序号(conn, 租约号)
            conn.execute(
                """INSERT OR IGNORE INTO 心跳缺口
                   (租约号,缺口序号,心跳号,时刻,处置态,是否超限,第几次拒延)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    租约号,
                    序号,
                    心跳号,
                    时刻,
                    态_超限拒延 if 超限 else 态_缺口已记,
                    1 if 超限 else 0,
                    连续数 if 超限 else 0,
                ),
            )
            if 超限:
                # 拒延双写两轨：候审影子只归档，放行不读
                _写候审影子(conn, 租约号, 序号, 心跳号, 时刻, 连续数)
                _留痕(conn, "心跳缺口", 租约号, f"第{连续数}次丢包·超限拒延时·缺口已记")
            else:
                _留痕(conn, "心跳缺口", 租约号, f"第{连续数}次丢包·缺口已记")
            回报["状态"] = row["状态"]
            回报["连续丢包数"] = 连续数
            回报["是否超限"] = 超限
            回报["缺口序号"] = 序号
            if 超限:
                回报["提示"] = f"第{连续数}次丢包已超上限{上限}，补发将拒延时，心跳缺口已记"
        conn.commit()
        return 回报
    finally:
        conn.close()


def 批量心跳(租约号列表: list[str]) -> list:
    out = []
    for lid in 租约号列表:
        try:
            out.append(发心跳({"租约号": lid}))
        except ValueError as e:
            out.append({"租约号": lid, "错误": str(e)})
    return out


def 补发缺口(body: dict) -> dict:
    """对连续丢包缺口做一次补发延时。

    放行轨读正式快照表（心跳缺口）未补偿行；拒延判定走心跳表连续段联查。
    两条读引用面拆开，不共用一个快照口。BEGIN IMMEDIATE 写锁 + 条件
    UPDATE 的 CAS，保证双会话抢补发一成一拒、缺口计数不互盖。
    """
    租约号 = 校验.租约号(body.get("租约号"))
    conn = 连接()
    conn.isolation_level = None  # 手管事务，BEGIN IMMEDIATE 立即取写锁
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM 租约 WHERE 租约号=?", (租约号,)).fetchone()
        if not row:
            raise ValueError("无此租约")
        if row["状态"] not in ("生效中", "已续约"):
            raise ValueError("当前状态不可补发")

        连续数 = 连续丢包次数(租约号, conn)
        上限 = 丢包上限()
        超限 = 连续数 > 上限

        # 放行轨单独一口：只取正式快照表中仍未处置的缺口
        待补 = conn.execute(
            "SELECT * FROM 心跳缺口 WHERE 租约号=? AND 处置态=? ORDER BY 缺口序号",
            (租约号, 态_缺口已记),
        ).fetchall()

        if 超限:
            拒延行 = conn.execute(
                """SELECT * FROM 心跳缺口 WHERE 租约号=? AND 是否超限=1
                   ORDER BY 缺口序号 DESC LIMIT 1""",
                (租约号,),
            ).fetchone()
            序号 = int(拒延行["缺口序号"]) if 拒延行 else _下一缺口序号(conn, 租约号)
            心跳号 = 拒延行["心跳号"] if 拒延行 else f"hb-{uuid.uuid4().hex[:8]}"
            if 拒延行:
                conn.execute(
                    "UPDATE 心跳缺口 SET 第几次拒延=? WHERE 租约号=? AND 缺口序号=?",
                    (连续数, 租约号, 序号),
                )
            else:
                conn.execute(
                    """INSERT OR IGNORE INTO 心跳缺口
                       (租约号,缺口序号,心跳号,时刻,处置态,是否超限,第几次拒延)
                       VALUES (?,?,?,?,?,?,?)""",
                    (租约号, 序号, 心跳号, 校验.此刻(), 态_超限拒延, 1, 连续数),
                )
            # 拒延双写两轨，读引用不同：影子仅候审归档
            _写候审影子(conn, 租约号, 序号, 心跳号, 校验.此刻(), 连续数)
            _留痕(conn, "缺口补发拒延", 租约号, f"第{连续数}次丢包超限·补偿已拒·缺口已记")
            conn.commit()
            raise ValueError(
                f"第{连续数}次丢包已超连续丢包上限{上限}，拒延时并标心跳缺口"
            )

        if not 待补:
            conn.commit()
            raise ValueError("无缺口可补发（缺口均已补偿或已闭合）")

        # 条件 UPDATE 即 CAS：仅当处置态仍为缺口已记才占位，并发第二方影响 0 行
        cur = conn.execute(
            "UPDATE 心跳缺口 SET 处置态='占位' WHERE 租约号=? AND 处置态=?",
            (租约号, 态_缺口已记),
        )
        if cur.rowcount != len(待补):
            conn.rollback()
            raise ValueError("缺口已被另一会话补偿，本次补发拒绝")

        心跳号 = f"hb-{uuid.uuid4().hex[:8]}"
        时刻 = 校验.此刻()
        延长 = int(body.get("延长分钟") or _默认延长分钟() // 4)
        延长 = 校验.正整数("延长分钟", 延长, 下限=1, 上限=24 * 60)
        新到期 = datetime.now(timezone.utc) + timedelta(minutes=延长)
        iso = 新到期.strftime("%Y-%m-%dT%H:%M:%SZ")

        # 成功补发本身也是一条成功心跳，落心跳表（说明带缺口补发指纹）
        conn.execute(
            """INSERT INTO 心跳(心跳号,租约号,时刻,结果,延迟毫秒,说明)
               VALUES (?,?,?,?,?,?)""",
            (心跳号, 租约号, 时刻, "成功", int(body.get("延迟毫秒") or 35), "缺口补发·延时成功"),
        )
        conn.execute(
            """UPDATE 心跳缺口 SET 处置态=?, 补偿心跳号=?, 补偿时=?
               WHERE 租约号=? AND 处置态='占位'""",
            (态_已补偿, 心跳号, 时刻, 租约号),
        )
        conn.execute(
            """UPDATE 租约 SET 状态='已续约', 到期时刻=?, 续约次数=续约次数+1, 更新时=?
               WHERE 租约号=?""",
            (iso, 时刻, 租约号),
        )
        _留痕(
            conn,
            "缺口补发成功",
            租约号,
            f"补偿{len(待补)}个缺口·续约次数+1",
        )
        conn.commit()
        return {
            "心跳号": 心跳号,
            "租约号": 租约号,
            "结果": "成功",
            "新到期时刻": iso,
            "补偿缺口数": len(待补),
            "连续丢包数": 0,
            "是否超限": False,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def 最近失败次数(租约号: str, 窗口: int = 5) -> int:
    conn = 连接()
    try:
        rows = conn.execute(
            "SELECT 结果 FROM 心跳 WHERE 租约号=? ORDER BY rowid DESC LIMIT ?",
            (租约号, 窗口),
        ).fetchall()
        return sum(1 for r in rows if r["结果"] != "成功")
    finally:
        conn.close()
