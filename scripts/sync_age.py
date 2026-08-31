#!/usr/bin/env python3
"""后台年龄同步：登录运营接口 -> 拉取用户列表 -> 按姓名匹配体验/订阅用户 -> 计算精确年龄 -> 内嵌到 index.html
用法:
  python3 sync_age.py send            # 向账号绑定手机发送验证码
  python3 sync_age.py login <code>    # 用验证码登录并同步年龄到 index.html
"""
import json, re, sys, os, urllib.request

BASE = "https://api-xintai.colofoo.com/admin"
ACCOUNT = "李成翰2"
TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pull_cache", "ops_token.json")

def api(path, method="GET", body=None, token=None):
    url = BASE + path
    req = urllib.request.Request(url, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("ops-token", token)
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as r:
            txt = r.read().decode()
    except urllib.error.HTTPError as e:
        txt = e.read().decode()
    j = json.loads(txt)
    if j.get("code") != 200:
        raise RuntimeError(j.get("msg") or f"接口错误 code={j.get('code')}")
    return j.get("data")

def calc_age(birthday, ref_date):
    if not birthday:
        return None
    from datetime import datetime
    try:
        b = datetime.strptime(str(birthday)[:10], "%Y-%m-%d")
        n = datetime.strptime(ref_date, "%Y-%m-%d")
        a = n.year - b.year
        if (n.month, n.day) < (b.month, b.day):
            a -= 1
        return a
    except Exception:
        return None

def send_code():
    r = api("/ops/auth/sendCode", "POST", {"account": ACCOUNT})
    print(f"验证码已发送至账号「{ACCOUNT}」绑定手机，2 分钟内有效。请把验证码发我。")

def login_and_sync(code):
    d = api("/ops/auth/login", "POST", {"account": ACCOUNT, "code": code})
    token = d.get("token")
    if not token:
        raise RuntimeError("登录成功但未返回 token")
    print(f"登录成功：{d.get('operatorName')} · {d.get('deptName')} · 可查部门 {d.get('scopeDeptCount')}")
    os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump({"token": token, "info": d, "loginAt": ""}, f, ensure_ascii=False)

    # 拉取用户列表
    all_users, page = [], 1
    while True:
        r = api(f"/ops/data/users?pageNum={page}&pageSize=200", token=token)
        recs = r.get("records") or []
        all_users.extend(recs)
        total = r.get("total") or len(all_users)
        if len(all_users) >= total or page > 60:
            break
        page += 1
    print(f"接口用户池：{len(all_users)} 人")

    # 读取当前看板数据
    idx = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "index.html")
    html = open(idx, encoding="utf-8").read()
    m = re.search(r'"refDate":\s*"([^"]+)"', html)
    ref_date = m.group(1) if m else "2026-08-28"
    # 用括号匹配解析 DATA 对象，提取体验/订阅姓名
    si = html.find("const DATA = ")
    if si < 0:
        raise RuntimeError("未找到 DATA 定义")
    depth, end = 0, None
    for k in range(si + len("const DATA = "), len(html)):
        if html[k] == "{":
            depth += 1
        elif html[k] == "}":
            depth -= 1
            if depth == 0:
                end = k + 1
                break
    data_obj = json.loads(html[si + len("const DATA = "):end])
    exp_names = [r[1] for r in (data_obj.get("exp") or []) if len(r) > 1 and r[1]]
    sub_names = [r[1] for r in (data_obj.get("sub") or []) if len(r) > 1 and r[1]]
    names = list(dict.fromkeys([n for n in exp_names + sub_names if n]))
    print(f"待匹配体验用户：{len(names)} 人")

    # 按姓名建索引（userName + nickName）
    by_name = {}
    for u in all_users:
        nm = (u.get("userName") or "").strip()
        nk = (u.get("nickName") or "").strip()
        if nm:
            by_name.setdefault(nm, []).append(u)
        if nk and nk != nm:
            by_name.setdefault(nk, []).append(u)

    sync, matched, multi, none = {}, 0, 0, 0
    for nm in names:
        cands = by_name.get(nm) or []
        if len(cands) == 1:
            age = calc_age(cands[0].get("birthday"), ref_date)
            if age is not None:
                sync[nm] = age
                matched += 1
            else:
                none += 1
        elif len(cands) > 1:
            multi += 1
        else:
            none += 1
    print(f"匹配：成功 {matched} · 未匹配 {none} · 重名待确认 {multi}")

    # 内嵌 ageSync 到 index.html 的 S 定义
    sync_json = json.dumps(sync, ensure_ascii=False, separators=(",", ":"))
    old = re.search(r"ageSync:\{.*?\}, ageSyncAt", html, re.S)
    if old:
        html = html[:old.start()] + f"ageSync:{sync_json}, ageSyncAt" + html[old.end():]
        open(idx, "w", encoding="utf-8").write(html)
        print(f"已内嵌 {len(sync)} 条年龄数据到 index.html")
    else:
        print("!! 未找到 ageSync 定义，跳过内嵌（请检查 index.html 结构）")

def sync_with_token():
    """用已保存 token 同步年龄（不重新登录）"""
    if not os.path.exists(TOKEN_FILE):
        print("无已保存 token，请先 send + login")
        return
    with open(TOKEN_FILE, encoding="utf-8") as f:
        token = json.load(f).get("token")
    if not token:
        print("token 为空")
        return
    # 复用 login_and_sync 的后半部分逻辑
    from datetime import datetime
    def _api(path, method="GET", body=None):
        return api(path, method, body, token=token)
    all_users, page = [], 1
    while True:
        r = _api(f"/ops/data/users?pageNum={page}&pageSize=200")
        recs = r.get("records") or []
        all_users.extend(recs)
        total = r.get("total") or len(all_users)
        if len(all_users) >= total or page > 60:
            break
        page += 1
    print(f"接口用户池：{len(all_users)} 人")
    idx = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "index.html")
    html = open(idx, encoding="utf-8").read()
    m = re.search(r'"refDate":\s*"([^"]+)"', html)
    ref_date = m.group(1) if m else "2026-08-28"
    si = html.find("const DATA = ")
    depth, end = 0, None
    for k in range(si + len("const DATA = "), len(html)):
        if html[k] == "{": depth += 1
        elif html[k] == "}":
            depth -= 1
            if depth == 0: end = k + 1; break
    data_obj = json.loads(html[si + len("const DATA = "):end])
    exp_names = [r[1] for r in (data_obj.get("exp") or []) if len(r) > 1 and r[1]]
    sub_names = [r[1] for r in (data_obj.get("sub") or []) if len(r) > 1 and r[1]]
    names = list(dict.fromkeys([n for n in exp_names + sub_names if n]))
    print(f"待匹配用户：{len(names)} 人")
    by_name = {}
    for u in all_users:
        nm = (u.get("userName") or "").strip()
        nk = (u.get("nickName") or "").strip()
        if nm: by_name.setdefault(nm, []).append(u)
        if nk and nk != nm: by_name.setdefault(nk, []).append(u)
    sync, matched, multi, none = {}, 0, 0, 0
    for nm in names:
        cands = by_name.get(nm) or []
        if len(cands) == 1:
            age = calc_age(cands[0].get("birthday"), ref_date)
            if age is not None: sync[nm] = age; matched += 1
            else: none += 1
        elif len(cands) > 1: multi += 1
        else: none += 1
    print(f"匹配：成功 {matched} · 未匹配 {none} · 重名待确认 {multi}")
    sync_json = json.dumps(sync, ensure_ascii=False, separators=(",", ":"))
    old = re.search(r"ageSync:\{.*?\}, ageSyncAt", html, re.S)
    if old:
        html = html[:old.start()] + f"ageSync:{sync_json}, ageSyncAt" + html[old.end():]
        open(idx, "w", encoding="utf-8").write(html)
        print(f"已内嵌 {len(sync)} 条年龄数据到 index.html")
    else:
        print("!! 未找到 ageSync 定义，跳过内嵌")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "send":
        send_code()
    elif cmd == "login" and len(sys.argv) > 2:
        login_and_sync(sys.argv[2])
    elif cmd == "sync":
        sync_with_token()
    else:
        print(__doc__)
