#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从飞书多维表拉取最新数据并写入经营看板（index.html 内嵌 DATA）。
用法：
  python3 scripts/pull_bitable.py [--index /path/to/index.html]
多维表链接默认使用用户提供的：
  https://ucn9pv6z2cnu.feishu.cn/base/B1wVbyEmjaBuNDsMsavcStSvnlc
运行前提：lark-cli 可用且已登录用户身份（--as user）。
"""
import subprocess, json, re, sys, os, datetime, argparse

BASE_TOKEN = "B1wVbyEmjaBuNDsMsavcStSvnlc"
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pull_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# 表映射：5 家社康 × 登记/体验/活动 + 订阅 + 目标管理 + 目标完成汇总
REG_TABLES = {
    "和联社康": "tblMKQtyuN1vkdDz",
    "吉祥里社康": "tblLp9RXP47Q5n1x",
    "民治社康": "tblAEvmKP0sXJsI8",
    "鹭湖社康": "tblKN5jfptuje6hK",
    "紫薇社康": "tblbjMT70HQ9LpRQ",
}
EXP_TABLES = {
    "和联社康": "tblSHMhqEmCn0yBK",
    "吉祥里社康": "tbltTA0rXK5c4v7D",
    "民治社康": "tblgOEPXS1ip29Gv",
    "鹭湖社康": "tbldtLItZAboFXMp",
    "紫薇社康": "tblSad0j1UwswOBy",
}
ACT_TABLES = {
    "和联社康": "tblPJOHm45fkct4L",
    "吉祥里社康": "tblgcw7KEXTcHeTF",
    "民治社康": "tblnBiPFhXspbKd4",
    "鹭湖社康": "tblrl5B25xiHM95m",
    "紫薇社康": "tblfwXvCFlfJabB2",
}
SUB_TABLE = "tblg8YU6WLLiUL46"
MT_TABLE = "tbl7hxOAd1UvZjaT"
WEEKLY_TABLE = "tbl1JtGQq4JvYZHb"
FUNNEL_TABLE = "tblNNxgyTvAtvoMN"


def run_cli(table_id, out):
    """拉取一张表的全量记录到 ndjson 文件（lark-cli 要求相对路径）。"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    fname = os.path.basename(out)
    cmd = ["lark-cli", "base", "+record-list", "--base-token", BASE_TOKEN,
           "--table-id", table_id, "--format", "ndjson", "--output", fname,
           "--overwrite", "--as", "user"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=CACHE_DIR)
    if r.returncode != 0:
        raise RuntimeError(f"拉取表 {table_id} 失败: {r.stderr[-500:]}")
    return os.path.join(CACHE_DIR, fname)


def read_ndjson(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def opt(v):
    """select/多选数组 → 第一个选项文本"""
    if not v:
        return ""
    if isinstance(v, list):
        return v[0] if v else ""
    return v


def date_only(v):
    """datetime 字符串 → yyyy-MM-dd"""
    if not v:
        return ""
    s = str(v)
    return s[:10] if len(s) >= 10 else s


def link_text(v):
    """link 字段 → 文本；可为 [{'text':'..','link':'..'}] 或 [{'text':'..'}] 或 []"""
    if not v:
        return ""
    if isinstance(v, list):
        parts = []
        for item in v:
            if isinstance(item, dict):
                parts.append(item.get("text") or item.get("link") or "")
            else:
                parts.append(str(item))
        return "".join(parts)
    if isinstance(v, dict):
        return v.get("text") or v.get("link") or ""
    return str(v)


def pull():
    counts = {}
    reg, exp, act, sub, weekly, mt, funnel = [], [], [], [], [], [], []

    # 登记表
    for sk, tid in REG_TABLES.items():
        out = os.path.join(CACHE_DIR, f"reg_{sk}.ndjson")
        run_cli(tid, out)
        rows = read_ndjson(out)
        for r in rows:
            f = r
            reg.append([sk, date_only(f.get("记录时间")), opt(f.get("用户来源")),
                        opt(f.get("性别")), opt(f.get("年龄段"))])
        counts[f"登记-{sk}"] = len(rows)

    # 体验表
    for sk, tid in EXP_TABLES.items():
        out = os.path.join(CACHE_DIR, f"exp_{sk}.ndjson")
        run_cli(tid, out)
        rows = read_ndjson(out)
        for r in rows:
            f = r
            exp.append([sk, f.get("用户姓名") or "", opt(f.get("用户分类")),
                        opt(f.get("体验产品")), opt(f.get("设备类型")),
                        date_only(f.get("佩戴体验开始时间")), date_only(f.get("佩戴体验结束时间")),
                        opt(f.get("退订原因")), link_text(f.get("来源活动")),
                        str(f.get("手机号") or "")])
        counts[f"体验-{sk}"] = len(rows)

    # 活动表（以多维表为准，空则清空，不保留旧数据）
    act_pulled = 0
    for sk, tid in ACT_TABLES.items():
        out = os.path.join(CACHE_DIR, f"act_{sk}.ndjson")
        run_cli(tid, out)
        rows = read_ndjson(out)
        for r in rows:
            f = r
            act.append([sk, f.get("活动名称") or "", opt(f.get("活动类型")), opt(f.get("活动状态")),
                        date_only(f.get("活动日期")), f.get("目标参与人数") or 0,
                        f.get("实际参与人数") or 0, f.get("活动成本") or 0, f.get("活动地点") or ""])
            act_pulled += 1
    counts["活动(多维表)"] = act_pulled

    # 订阅表
    out = os.path.join(CACHE_DIR, "sub.ndjson")
    run_cli(SUB_TABLE, out)
    sub_rows = read_ndjson(out)
    counts["订阅"] = len(sub_rows)
    # 订阅表字段含各社康 link，此处先按空处理（当前无记录）

    # 目标完成汇总表
    out = os.path.join(CACHE_DIR, "weekly.ndjson")
    run_cli(WEEKLY_TABLE, out)
    for r in read_ndjson(out):
        weekly.append([opt(r.get("所属维度")), opt(r.get("周次")), opt(r.get("阶段")),
                       r.get("目标值") or 0, r.get("实际值") or 0])
    counts["目标完成汇总"] = len(weekly)

    # 目标管理表
    out = os.path.join(CACHE_DIR, "mt.ndjson")
    run_cli(MT_TABLE, out)
    for r in read_ndjson(out):
        mt.append([r.get("目标名称") or "", r.get("8月") or 0, r.get("9月") or 0,
                   r.get("10月") or 0, r.get("11月") or 0])
    counts["目标管理"] = len(mt)

    # 漏斗汇总表（参考，不写入 DATA，仅计数）
    out = os.path.join(CACHE_DIR, "funnel.ndjson")
    run_cli(FUNNEL_TABLE, out)
    counts["漏斗汇总"] = len(read_ndjson(out))

    return reg, exp, act, sub, weekly, mt, counts


def build_data(reg, exp, act, sub, weekly, mt):
    import calendar
    sk_list = ["和联社康", "吉祥里社康", "民治社康", "鹭湖社康", "紫薇社康"]
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    # 数据截止日 = 明细表实际最新日期（登记记录时间 / 体验开始时间 取最大）
    reg_dates = [r[1] for r in reg if len(r) > 1 and r[1]]
    exp_dates = [r[5] for r in exp if len(r) > 5 and r[5]]
    pool = [d for d in reg_dates + exp_dates if d]
    ref_date = max(pool) if pool else datetime.date.today().strftime("%Y-%m-%d")
    ref = datetime.datetime.strptime(ref_date, "%Y-%m-%d").date()
    ref_cn = f"{ref.year}年{ref.month}月{ref.day}日 周{'一二三四五六日'[ref.weekday()]}"

    # 本周（自然周 周一~周日）
    mon = ref - datetime.timedelta(days=ref.weekday())
    sun = mon + datetime.timedelta(days=6)
    # 周次标签：当月第几周（含当月1日的自然周为 W1）
    first = ref.replace(day=1)
    w1 = first - datetime.timedelta(days=first.weekday())
    wn = ((ref - w1).days // 7) + 1
    week = f"{ref.month}月W{wn}"

    # 本月
    month = f"{ref.month}月"
    month_cn = f"{ref.year}年{ref.month}月"
    month_start = f"{ref.year}-{ref.month:02d}-01"
    month_end = f"{ref.year}-{ref.month:02d}-{calendar.monthrange(ref.year, ref.month)[1]:02d}"

    # 目标完成汇总实际覆盖到的周次：取「实际值>0 的最新周次」（未来周次仅计划、实际为 0，不计入）
    weeks = [r[1] for r in weekly if len(r) > 1 and r[1]]
    active_weeks = [r[1] for r in weekly if len(r) > 4 and r[1] and (r[4] or 0) > 0]
    target_thru = max(active_weeks) if active_weeks else (max(weeks) if weeks else "—")

    meta = {
        "refDate": ref_date,
        "refDateCN": ref_cn,
        "month": month,
        "monthCN": month_cn,
        "week": week,
        "weekStart": mon.strftime("%Y-%m-%d"),
        "weekEnd": sun.strftime("%Y-%m-%d"),
        "monthStart": month_start,
        "monthEnd": month_end,
        "targetThru": target_thru,
        "noteTarget": f"目标与实际按《目标完成汇总表》口径（目标已同步至 {target_thru}）；本日/本周/本月新增按明细表实时统计。",
        "src": "飞书多维表",
        "srcAt": now,
    }
    return {"meta": meta, "sk": sk_list, "reg": reg, "exp": exp, "act": act,
            "sub": sub, "weekly": weekly, "mt": mt}


def write_back(index_path, data):
    html = open(index_path, encoding="utf-8").read()
    pat = re.compile(r'const DATA = (\{.*?\});\n', re.S)
    m = pat.search(html)
    if not m:
        raise RuntimeError("index.html 中未找到 const DATA")
    # 以多维表为准：活动/订阅表为空则直接清空，不保留看板旧数据（避免展示过时/未办的活动记录）
    new_data = json.dumps(data, ensure_ascii=False)
    html2 = pat.sub(lambda _: f"const DATA = {new_data};\n", html, count=1)
    open(index_path, "w", encoding="utf-8").write(html2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "index.html"))
    args = ap.parse_args()
    reg, exp, act, sub, weekly, mt, counts = pull()
    data = build_data(reg, exp, act, sub, weekly, mt)
    write_back(args.index, data)
    print("已从飞书多维表拉取并写入看板：")
    for k, v in counts.items():
        print(f"  {k}: {v} 条")
    print(f"  → 登记 {len(reg)} · 体验 {len(exp)} · 活动 {len(act)} · 订阅 {len(sub)} · 周目标 {len(weekly)} · 月度目标 {len(mt)}")
    print(f"  拉取时间: {data['meta']['srcAt']}")
    print(f"  写入: {args.index}")
    # 覆盖上传到飞书云空间，保持固定链接不变
    import subprocess
    feishu_file_token = "FRIFbuYGPoRjgaxpc6lc1DMFnMc"
    feishu_url = "https://ucn9pv6z2cnu.feishu.cn/file/FRIFbuYGPoRjgaxpc6lc1DMFnMc"
    try:
        r = subprocess.run(
            ["lark-cli", "drive", "+upload", "--file", os.path.relpath(args.index, os.getcwd()),
             "--file-token", feishu_file_token,
             "--name", "社康健康经营看板.html", "--as", "user"],
            capture_output=True, text=True, timeout=180)
        if '"ok": true' in r.stdout:
            print(f"  飞书云空间已覆盖更新（固定链接不变）：{feishu_url}")
        else:
            print("  飞书云空间覆盖更新失败（本地文件已更新，可稍后手动覆盖）：")
            print("  " + (r.stdout + r.stderr).strip()[-300:])
    except Exception as e:
        print(f"  飞书云空间覆盖更新异常（本地文件已更新）：{e}")


if __name__ == "__main__":
    main()
