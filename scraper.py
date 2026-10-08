from playwright.sync_api import sync_playwright
import pandas as pd


# Имя функции изменено на fetch_tournament (в единственном числе)
def fetch_tournament(url: str) -> dict:
    """Возвращает словарь с данными турнира: {'title': ..., 'df': DataFrame}"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"))
        page.goto(url, wait_until="domcontentloaded")

        # ждём, пока JS отрисует строки таблицы
        page.wait_for_selector(
            "table.tournament-results tbody tr.row", timeout=30000)

        # === ЧТО ИЗМЕНИЛОСЬ ===
        # Убрали цикл for sec in page.query_selector_all(...)
        # Теперь берем только самую первую секцию результатов на странице
        sec = page.query_selector("section.group-results")
        if not sec:
            browser.close()
            raise ValueError("Таблица турнира не найдена на странице")

        title_el = sec.query_selector(".tournament-title")
        title = title_el.inner_text().strip().replace("\n", " ") if title_el else ""

        rows = []
        for tr in sec.query_selector_all("table.tournament-results tbody tr.row"):
            cells = [td.inner_text().strip().replace("\n", " ")
                     for td in tr.query_selector_all("td")]
            rows.append(cells)

        browser.close()  # Закрываем браузер сразу после парсинга

        if not rows:
            raise ValueError("Таблица турнира пуста")

        n = len(rows)  # число игроков
        cols = (["Игрок", "_diag"]
                + [f"vs_{i}" for i in range(1, n)]
                + ["Очки", "Место"])

        # на случай, если число столбцов отличается — подстрахуемся
        width = len(rows[0])
        if width != len(cols):
            cols = [f"c{i}" for i in range(width)]

        df = pd.DataFrame(rows, columns=cols)

        # Возвращаем просто словарь, а не список со словарями
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