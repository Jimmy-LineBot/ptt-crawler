# -*- coding: utf-8 -*-
"""
PTT Stock 板 今日/昨日文章 + 推文 爬蟲 (擬人化版本)
--------------------------------------------------------
說明:
  使用 PyPtt 透過 WebSocket 連線 PTT，抓取 Stock 板今天與昨天的文章。
  本版本加入多種擬人化機制，讓行為模式更接近真人操作。

需要安裝的套件:
  pip install PyPtt

擬人化機制:
  - 啟動時隨機等待 0~60 秒，避免每次固定時間執行
  - 每篇文章之間的延遲模擬人類閱讀節奏（偶爾快偶爾慢）
  - 每 20~30 篇會停下來休息 15~45 秒
  - 不從最新一篇開始，隨機跳過前幾篇
  - 冷卻時間 8 小時，一天最多跑 1~2 次
"""

import sys
import time
import random
import getpass
import datetime
from pathlib import Path

try:
    import PyPtt
except ImportError:
    print("找不到 PyPtt 套件,請先執行: pip install PyPtt")
    input("按 Enter 結束...")
    sys.exit(1)

BOARD = "Stock"
MAX_BACK = 200
COOLDOWN_HOURS = 8
LAST_RUN_FILE = Path.cwd() / f".ptt_{BOARD}_last_run.txt"

def human_delay():
    """模擬人類閱讀速度的隨機延遲"""
    base = random.uniform(1.5, 3.5)
    # 15% 機率多停久一點（模擬人在看文章內容）
    if random.random() < 0.15:
        base += random.uniform(3.0, 8.0)
    # 5% 機率停很久（模擬人去做別的事）
    if random.random() < 0.05:
        base += random.uniform(10.0, 20.0)
    time.sleep(base)

def check_cooldown():
    """檢查距離上次執行是否太近"""
    if not LAST_RUN_FILE.exists():
        return True

    try:
        last_run_str = LAST_RUN_FILE.read_text(encoding="utf-8").strip()
        last_run = datetime.datetime.fromisoformat(last_run_str)
    except Exception:
        return True

    elapsed = datetime.datetime.now() - last_run
    if elapsed < datetime.timedelta(hours=COOLDOWN_HOURS):
        remaining = datetime.timedelta(hours=COOLDOWN_HOURS) - elapsed
        minutes = int(remaining.total_seconds() // 60)
        print(f"提醒: 距離上次執行只過了 {elapsed}, 建議至少間隔 {COOLDOWN_HOURS} 小時再跑,")
        print(f"      以降低帳號被 PTT 系統判定異常的風險(還需等待約 {minutes} 分鐘)。")
        answer = input("仍要繼續執行嗎?(y/N): ").strip().lower()
        if answer != "y":
            print("已取消本次執行。")
            return False
    return True

def record_run_time():
    try:
        LAST_RUN_FILE.write_text(datetime.datetime.now().isoformat(), encoding="utf-8")
    except Exception:
        pass

def get_post_date(post):
    """嘗試從文章物件取得日期,回傳 datetime.date"""
    raw = None
    for key in ("date", "post_date", "time", "post_time", "datetime"):
        try:
            raw = post.get(key)
        except AttributeError:
            raw = None
        if raw:
            break
    if raw is None:
        return None
    if isinstance(raw, datetime.datetime):
        return raw.date()
    if isinstance(raw, datetime.date):
        return raw
    if isinstance(raw, str):
        for fmt in ("%a %b %d %H:%M:%S %Y", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y", "%m/%d"):
            try:
                parsed = datetime.datetime.strptime(raw.strip(), fmt)
                if "%Y" not in fmt:
                    parsed = parsed.replace(year=datetime.date.today().year)
                return parsed.date()
            except ValueError:
                continue
    return None

PUSH_TAG_MAP = {
    "PUSH": "推",
    "ARROW": "→",
    "BOO": "噓",
}

def push_to_text(push):
    """把單一推文物件轉成可讀字串"""
    if isinstance(push, str):
        return f"  {push}"

    def _get(*keys):
        for k in keys:
            try:
                if hasattr(push, "get"):
                    v = push.get(k)
                else:
                    v = getattr(push, k, None)
                if v not in (None, ""):
                    return v
            except Exception:
                pass
        return ""

    tag = _get("type", "tag", "push_type")
    tag = getattr(tag, "value", tag)
    tag = getattr(tag, "name", tag)
    tag = PUSH_TAG_MAP.get(str(tag), str(tag))
    user = _get("author", "user_id", "push_userid")
    content = _get("content", "push_content")
    ptime = _get("time", "ip_datetime", "push_ipdatetime", "date")
    return f"  {tag} {user}: {content} {ptime}".strip()

def main():
    if not check_cooldown():
        return

    # === 擬人化: 啟動前隨機等待 ===
    startup_wait = random.uniform(5, 60)
    print(f"準備中...({int(startup_wait)} 秒後開始)")
    time.sleep(startup_wait)

    ptt_id = input("PTT 帳號: ").strip()
    ptt_pw = getpass.getpass("PTT 密碼: ")

    ptt_bot = PyPtt.API()

    print("登入中...")
    try:
        ptt_bot.login(ptt_id, ptt_pw)
    except PyPtt.exceptions.LoginError as e:
        print(f"登入失敗: {e}")
        return
    except PyPtt.exceptions.WrongIDorPassword:
        print("帳號或密碼錯誤")
        return
    except Exception as e:
        print(f"登入時發生未預期的錯誤: {type(e).__name__}: {e}")
        return

    record_run_time()

    # === 擬人化: 登入後停一下再動作 ===
    login_pause = random.uniform(2.0, 5.0)
    time.sleep(login_pause)

    print("登入成功,開始搜尋 Stock 板今天/昨天的文章...")

    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    target_dates = {today, yesterday}

    try:
        newest_index = ptt_bot.get_newest_index(PyPtt.NewIndex.BOARD, board=BOARD)
    except Exception as e:
        print(f"取得看板最新索引失敗: {e}")
        try:
            ptt_bot.logout()
        except Exception:
            pass
        return

    # === 擬人化: 不從最新一篇開始,隨機跳過幾篇 ===
    skip = random.randint(0, 5)
    index = newest_index - skip

    articles = []
    checked = 0
    stop = False
    error_count = 0

    # === 擬人化: 每批次休息的間隔隨機決定 ===
    batch_size = random.randint(20, 30)

    while index > 0 and checked < MAX_BACK and not stop:

        # === 擬人化: 每抓一批就休息一下 ===
        if checked > 0 and checked % batch_size == 0:
            pause = random.uniform(15, 45)
            print(f"  (休息 {int(pause)} 秒...)")
            time.sleep(pause)
            # 下一批的間隔重新隨機
            batch_size = checked + random.randint(20, 30)

        try:
            post = ptt_bot.get_post(board=BOARD, index=index)
        except Exception:
            error_count += 1
            index -= 1
            checked += 1
            continue

        if post is None:
            index -= 1
            checked += 1
            continue

        post_date = get_post_date(post)
        checked += 1
        title = post.get("title", "(無標題)")

        if post_date in target_dates:
            print(f"  [符合] {title}")
            articles.append(post)
        elif post_date is not None and post_date < yesterday:
            stop = True

        index -= 1

        # === 擬人化: 用模擬人類速度的延遲 ===
        human_delay()

    if error_count:
        print(f"({error_count} 篇文章讀取失敗或已刪除,已自動略過)")

    # === 擬人化: 登出前停一下 ===
    time.sleep(random.uniform(1.0, 3.0))

    try:
        ptt_bot.logout()
    except Exception:
        pass

    if not articles:
        print("沒有抓到任何符合日期的文章。")
        return

    articles.sort(key=lambda p: get_post_date(p) or datetime.date.min)

    out_name = f"Stock_{yesterday.strftime('%Y%m%d')}_{today.strftime('%Y%m%d')}.txt"
    out_path = Path.cwd() / out_name

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"PTT Stock 板 抓取範圍: {yesterday} ~ {today}
")
        f.write(f"共 {len(articles)} 篇文章
")
        f.write("=" * 60 + "

")

        for i, post in enumerate(articles, 1):
            f.write(f"【第 {i} 篇】
")
            f.write(f"標題: {post.get('title', '')}
")
            f.write(f"作者: {post.get('author', '')}
")
            f.write(f"日期: {get_post_date(post)}
")
            f.write("-" * 60 + "
")
            f.write(f"{post.get('content', '')}
")
            f.write("-" * 60 + "
")

            pushes = post.get("comments", [])

            if pushes:
                f.write(f"推文 ({len(pushes)} 則):
")
                for p in pushes:
                    f.write(push_to_text(p) + "
")
            else:
                f.write("推文: (無)
")

            f.write("
" + "=" * 60 + "

")

    print(f"
完成!已將 {len(articles)} 篇文章存到:
{out_path}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"
發生錯誤: {e}")
    finally:
        input("
按 Enter 鍵結束...")
        sys.exit(0)
