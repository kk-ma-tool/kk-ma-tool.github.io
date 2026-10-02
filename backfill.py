# 乖乖值計算器：補抓 2021 年起的全部收盤價，存到 data/hist（每月一個檔），並抓官方除權息資料
# 每次執行有時間上限，沒抓完的下次會接著抓；全部抓完後，每天只補當天
import json, os, re, time, datetime as dt
import update as U

H = os.path.join('data', 'hist')
START = dt.date(2021, 1, 4)
BUDGET = float(os.environ.get('BUDGET_MIN', '270')) * 60
T0 = time.time()

def jload(p, d):
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else d

def jsave(p, o):
    with open(p, 'w', encoding='utf-8') as fo:
        json.dump(o, fo, ensure_ascii=False, separators=(',', ':'))

def ymd(d):
    return d.strftime('%Y%m%d')

def twse_ex(a, b):
    """證交所除權除息計算結果表：回傳 {code: [[日期, 參考價/前收盤], ...]}"""
    j = U.get(f'https://www.twse.com.tw/rwd/zh/exRight/TWT49U?startDate={a}&endDate={b}&response=json')
    fl = [str(x) for x in (j.get('fields') or [])]
    data = j.get('data') or []
    if not fl:
        for t in j.get('tables') or []:
            fl = [str(x) for x in (t.get('fields') or [])]; data = t.get('data') or []
            if fl: break
    idx = lambda n: next((i for i, x in enumerate(fl) if n in x), -1)
    iD, iC, iP, iR = idx('資料日期'), idx('股票代號'), idx('除權息前收盤價'), idx('除權息參考價')
    out = {}
    if min(iD, iC, iP, iR) < 0:
        print('  TWT49U 欄位不符', fl[:8], 'stat', j.get('stat'))
        return out
    for r in data:
        g = re.findall(r'\d+', str(r[iD])); p, q = U.num(r[iP]), U.num(r[iR])
        if len(g) < 3 or not p or not q:
            continue
        y = int(g[0]) + (1911 if int(g[0]) < 1911 else 0)
        out.setdefault(str(r[iC]).strip(), []).append([y * 10000 + int(g[1]) * 100 + int(g[2]), round(q / p, 6)])
    return out

def merge(ex, add):
    n = 0
    for c, lst in add.items():
        old = {z[0]: z for z in ex.get(c, [])}
        for z in lst:
            if old.get(z[0]) != z: n += 1
            old[z[0]] = z
        ex[c] = sorted(old.values(), key=lambda z: z[0])
    return n

def main():
    os.makedirs(H, exist_ok=True)
    prog = jload(os.path.join(H, 'progress.json'), {'done': [], 'ex_years': []})
    done = set(prog['done'])
    ex = jload(os.path.join(H, 'ex.json'), {})
    today = dt.datetime.now(U.TW).date()
    # 1) 官方除權息資料：歷年各抓一次（一年一次查詢），最近 60 天每次都重抓
    spans = [(dt.date(y, 1, 1), min(dt.date(y, 12, 31), today)) for y in range(START.year, today.year + 1) if y not in prog['ex_years']]
    spans.append((today - dt.timedelta(days=60), today))
    for a, b in spans:
        for name, fn in (('上市', twse_ex), ('上櫃', U.tpex_ex)):
            try:
                got = fn(ymd(a), ymd(b))
                print('除權息', name, ymd(a), '~', ymd(b), '：', sum(len(v) for v in got.values()), '筆，新增／更新', merge(ex, got))
                ok = bool(got)
            except Exception as e:
                print('除權息', name, ymd(a), '失敗', e); ok = False
            if b.year < today.year and ok and name == '上市' and a.year not in prog['ex_years']:
                prog['ex_years'].append(a.year)
    jsave(os.path.join(H, 'ex.json'), ex)
    # 2) 每天收盤價
    day, cache, cnt = START, {}, 0
    while day <= today:
        if time.time() - T0 > BUDGET:
            print('時間到，下次接著抓'); break
        k = int(ymd(day))
        if day.weekday() < 5 and k not in done and not (day == today and dt.datetime.now(U.TW).hour < 14):
            try:
                a, b = U.twse(ymd(day)), U.tpex(ymd(day))
            except Exception as e:
                print(k, '抓取失敗，下次再試', e); day += dt.timedelta(days=1); continue
            if a and b:
                ym = k // 100
                if ym not in cache:
                    cache[ym] = jload(os.path.join(H, f'{ym}.json'), {'d': [], 'c': {}})
                m = cache[ym]
                if k not in m['d']:
                    m['d'].append(k); m['d'].sort()
                i = m['d'].index(k)
                for c in m['c']:
                    if len(m['c'][c]) < len(m['d']):
                        m['c'][c].insert(i, None)
                for c, (nm, p, x) in list(a.items()) + list(b.items()):
                    arr = m['c'].setdefault(c, [None] * len(m['d']))
                    arr[i] = p
                jsave(os.path.join(H, f'{ym}.json'), m)
                cnt += 1
                print(k, '上市', len(a), '上櫃', len(b))
            elif not a and not b and day < today:
                print(k, '休市')
            else:
                print(k, '只抓到一邊，下次再試'); day += dt.timedelta(days=1); continue
            if True:
                done.add(k)
                prog['done'] = sorted(done)
                jsave(os.path.join(H, 'progress.json'), prog)
        day += dt.timedelta(days=1)
    left = sum(1 for i in range((today - START).days) if (START + dt.timedelta(days=i)).weekday() < 5 and int(ymd(START + dt.timedelta(days=i))) not in done)
    print('本次補抓', cnt, '天；還沒抓的平日', left, '天')

if __name__ == '__main__':
    main()
