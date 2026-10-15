from playwright.sync_api import sync_playwright
import pandas as pd


def fetch_tournament(url: str) -> dict:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"))
        
        # === ИЗМЕНЕНИЕ 1 ===
        # Меняем wait_until на networkidle, чтобы дождаться окончания фоновых запросов
        page.goto(url, wait_until="networkidle")
        
        page.wait_for_selector(
            "table.tournament-results tbody tr.row", timeout=30000)

        # === ИЗМЕНЕНИЕ 2 ===
        # Жестко ждем 2 секунды после появления таблицы, чтобы текст 100% отрисовался
        page.wait_for_timeout(2000)

        sec = page.query_selector("section.group-results")
        if not sec:
            browser.close()
            raise ValueError("Таблица турнира не найдена на странице")

        title_el = sec.query_selector(".tournament-title")
        # Тут тоже используем text_content(), он надежнее
        title = title_el.text_content().strip().replace("\n", " ") if title_el else ""

        rows = []
        for tr in sec.query_selector_all("table.tournament-results tbody tr.row"):
            # === ИЗМЕНЕНИЕ 3 ===
            # Меняем inner_text() на text_content(), он лучше достает текст в headless-режиме
            cells = [td.text_content().strip().replace("\n", " ")
                     for td in tr.query_selector_all("td")]
            rows.append(cells)
            
        browser.close()

        # Добавим проверку, чтобы не возвращать пустые массивы
        if not rows or all(all(c == '' for c in row) for row in rows):
            raise ValueError("Сайт вернул пустую таблицу, данные не прогрузились")

        n = len(rows)  
        cols = (["Игрок", "_diag"]
                + [f"vs_{i}" for i in range(1, n)]
                + ["Очки", "Место"])
        
        width = len(rows[0])
        if width != len(cols):
            cols = [f"c{i}" for i in range(width)]
            
        df = pd.DataFrame(rows, columns=cols)
        
        return {"title": title, "df": df}


def parse_score(s: str):
    """'3 : 0' -> (3, 0); пустое -> None"""
    try:
        a, b = s.split(":")
        return int(a), int(b)
    except Exception:
        return None


if __name__ == "__main__":
    import sys
    import json

    sys.stdout.reconfigure(encoding="utf-8")

    # === ЧТО ИЗМЕНИЛОСЬ ===
    data = fetch_tournament(sys.argv[1])

    # Формируем и выводим ОДИН словарь (а не список с помощью генератора)
    out = {"title": data["title"], "df": data["df"].to_dict(orient="split")}

    print(json.dumps(out, ensure_ascii=False))