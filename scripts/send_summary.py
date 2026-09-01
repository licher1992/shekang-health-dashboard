#!/usr/bin/env python3
"""经营看板自动更新后，向飞书【MVP管理群】发送简短经营总结（目标达成情况等）。
由 update_deploy.sh 在数据更新并推送后调用。
"""
import json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, "index.html")
CHAT_ID = "oc_d551e1380d5703070176427f81348593"   # MVP管理群
BOARD_URL = "https://licher1992.github.io/shekang-health-dashboard/"
LAST_FILE = os.path.join(ROOT, "pull_cache", "last_summary.json")


def load_data():
    html = open(INDEX, encoding="utf-8").read()
    si = html.find("const DATA = ")
    if si < 0:
        raise RuntimeError("index.html 未找到 DATA")
    depth = end = 0
    for k in range(si + len("const DATA = "), len(html)):
        if html[k] == "{":
            depth += 1
        elif html[k] == "}":
            depth -= 1
            if depth == 0:
                end = k + 1
                break
    return json.loads(html[si + len("const DATA = "):end])


def build_summary(d):
    M = d["meta"]
    reg, exp, sub = d["reg"], d["exp"], d["sub"]
    ms = M["monthStart"][:7]

    def cnt(rows, idx):
        return sum(1 for r in rows if len(r) > idx and r[idx] and r[idx][:7] == ms)

    def tod(rows, idx):
        return sum(1 for r in rows if len(r) > idx and r[idx] == M["refDate"])

    t_tot, t_mon, t_tod = len(reg), cnt(reg, 1), tod(reg, 1)
    e_tot, e_mon, e_tod = len(exp), cnt(exp, 5), tod(exp, 5)
    s_tot, s_mon, s_tod = len(sub), cnt(sub, 0), tod(sub, 0)

    def month_goal(stage, dim="总体"):
        # 周目标为当月累计值：取当月最后一周（W 编号最大）的目标与实际
        best = None; bestN = -1
        for w in d["weekly"]:
            if len(w) > 4 and w[0] == dim and w[2] == stage and w[1].startswith(M["month"]):
                mm = re.search(r"W(\d+)", w[1])
                n = int(mm.group(1)) if mm else 0
                if n > bestN:
                    bestN = n; best = w
        return (best[3], best[4]) if best else (0, 0)

    ct, ca = month_goal("触达")
    et, ea = month_goal("体验")

    # 分社康明细：本月触达/体验新增 + 对应目标
    sk_lines = []
    for sk in d["sk"]:
        tm = sum(1 for r in reg if r[0] == sk and len(r) > 1 and r[1][:7] == ms)
        em = sum(1 for r in exp if r[0] == sk and len(r) > 5 and r[5][:7] == ms)
        sct, sca = month_goal("触达", sk)
        set_, sea = month_goal("体验", sk)
        sk_lines.append(f"· {sk}：触达 {tm}/{sct} · 体验 {em}/{set_}")
    sk_detail = "\n".join(sk_lines)

    ev_t = None
    for m in d["mt"]:
        if m[0] == "总体-体验":
            idx = {8:1, 9:2, 10:3, 11:4}.get(int(M["month"].replace("月", "")))
            ev_t = m[idx] if (idx is not None and idx < len(m)) else None
            break
    if ev_t is None:
        ev_t = et

    def pct(a, t):
        return f"{round(a / t * 100)}%" if t else "—"

    alert = ""
    if s_tot == 0:
        alert = "\n⚠️ 订阅暂无数据，请检查订阅表录入。"
    elif ca / ct < 0.3 if ct else False:
        alert = "\n⚠️ 触达目标完成率偏低，请关注拉新进度。"

    lines = [
        f"**📊 社康经营看板 · 数据截止 {M.get('refDateCN', M.get('refDate'))}**",
        f"多维表拉取 {M.get('srcAt', '—')}",
        "",
        f"**■ 漏斗累计**：触达 {t_tot} · 体验 {e_tot} · 订阅 {s_tot}",
        f"**■ 本月新增**：触达 {t_mon} · 体验 {e_mon} · 订阅 {s_mon}",
        f"**■ 今日新增**：触达 {t_tod} · 体验 {e_tod} · 订阅 {s_tod}",
        "",
        "**■ 目标达成（本月）**",
        f"· 触达：目标 {ct} → 完成 {ca}（{pct(ca, ct)}）",
        f"· 体验新增：目标 {ev_t} → 完成 {ea}（{pct(ea, ev_t)}）",
        "",
        "**■ 分社康（本月触达/体验 · 目标）**",
        sk_detail,
        alert,
        "",
        f"看板：{BOARD_URL}",
    ]
    return "\n".join(lines)


def main():
    d = load_data()
    msg = build_summary(d)
    print(msg)
    if "--dry" in sys.argv:
        print("[dry-run] 不实际发送")
        return
    # 去重：同一次数据快照（srcAt）只发送一次，避免多个更新任务重复发送
    src_at = d["meta"].get("srcAt", "")
    try:
        last = json.load(open(LAST_FILE, encoding="utf-8")) if os.path.exists(LAST_FILE) else {}
    except Exception:
        last = {}
    if last.get("srcAt") == src_at:
        print(f"数据快照未变化（srcAt={src_at}），跳过重复发送")
        return
    cmd = ["lark-cli", "im", "+messages-send", "--chat-id", CHAT_ID, "--markdown", msg]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("发送失败:", r.stderr[:600])
        raise SystemExit(1)
    os.makedirs(os.path.dirname(LAST_FILE), exist_ok=True)
    json.dump({"srcAt": src_at}, open(LAST_FILE, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"✅ 已发送到【MVP管理群】(chat={CHAT_ID})")


if __name__ == "__main__":
    main()
