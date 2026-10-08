import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

SCRAPER = Path(__file__).parent / "scraper.py"


@st.cache_data(show_spinner="Загружаю турнир...", ttl=600)
def load_tournament(url: str) -> pd.DataFrame:  # Изменили аннотацию типа (теперь возвращает DataFrame)
    r = subprocess.run(
        [sys.executable, str(SCRAPER), url],
        capture_output=True, text=True, encoding="utf-8", timeout=90, )
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-1500:])

    data = json.loads(r.stdout)

    # === ЧТО ИЗМЕНИЛОСЬ ===
    # Если scraper.py всё ещё возвращает список (где теперь только 1 элемент)
    if isinstance(data, list) and len(data) > 0:
        return pd.DataFrame(**data[0]["df"])
    # Если scraper.py тоже переделали, и он теперь возвращает сразу словарь
    elif isinstance(data, dict):
        return pd.DataFrame(**data["df"])
    else:
        raise ValueError("Неожиданный формат данных от скрапера или таблица не найдена")


def calculate_transactions(dfs):
    # === ЧТО ДОБАВЛЕНО: Шаг 0 ===
    # 1. Объединяем список датафреймов в один общий
    combined_df = pd.concat(dfs, ignore_index=True)

    # 2. Группируем по имени игрока и суммируем их балансы за все турниры
    # Это нужно, чтобы если игрок в одном турнире должен 100, а в другом ему должны 150,
    # итоговый баланс составил +50.
    aggregated = combined_df.groupby('Игрок', as_index=False)['Забрать/дать в деньгах'].sum()
    # ==============================

    # === ЧТО ИЗМЕНЕНО ===
    # Заменили `df` на `aggregated` в фильтрации
    debtors = aggregated[aggregated['Забрать/дать в деньгах'] <
                         0].set_index('Игрок')['Забрать/дать в деньгах'].abs().to_dict()
    creditors = aggregated[aggregated['Забрать/дать в деньгах'] >
                           0].set_index('Игрок')['Забрать/дать в деньгах'].to_dict()
    # ====================

    transactions = []

    # Шаг 1: Ищем точные совпадения (например, -250 и +250)
    # (логика осталась без изменений)
    for d_name, d_amt in list(debtors.items()):
        for c_name, c_amt in list(creditors.items()):
            if d_amt == c_amt and d_amt > 0:
                transactions.append(
                    f"{d_name} отдает {d_amt:.0f} грн -> {c_name}")
                debtors[d_name] = 0
                creditors[c_name] = 0
                break

    # Убираем из списков тех, чей баланс уже сведен к нулю
    debtors = {k: v for k, v in debtors.items() if v > 0}
    creditors = {k: v for k, v in creditors.items() if v > 0}

    # Шаг 2: Распределяем оставшиеся долги (если точных совпадений нет)
    # (логика осталась без изменений)
    for d_name in list(debtors.keys()):
        while debtors[d_name] > 0 and creditors:
            c_name = list(creditors.keys())[0]
            c_amt = creditors[c_name]

            amount = min(debtors[d_name], c_amt)
            transactions.append(
                f"{d_name} отдает {amount:.0f} грн -> {c_name}")

            debtors[d_name] -= amount
            creditors[c_name] -= amount

            if creditors[c_name] == 0:
                del creditors[c_name]

    return transactions


st.title("SETKA: расчёт метрик")

url1 = st.text_input(
    "Ссылка на страницу турнира 1")
url2 = st.text_input("Ссылка на страницу турнира 2")
url3 = st.text_input("Ссылка на страницу турнира 3")
url4 = st.text_input("Ссылка на страницу турнира 4")
url5 = st.text_input("Ссылка на страницу турнира 5")


reward_win_uah = 100
everyone_wins = 2.5

if st.button("Посчитать", type="primary"):
    try:
        urls = [url1, url2, url3, url4, url5]
        tournaments = [load_tournament(url) for url in urls if url != ""]
    except Exception as e:
        st.error("Не удалось загрузить страницу")
        st.code(str(e))
    else:
        if not tournaments:
            st.warning("Турниры не найдены")
        for df in tournaments:
            # Расчет и добавление новых столбцов
            target_cols = ['_diag', 'vs_1', 'vs_2', 'vs_3', 'vs_4', 'vs_5']
            df['Кол. побед'] = sum(df[col].str.startswith('3', na=False)
                                   for col in target_cols)
            df['Не хватает до 2,5'] = everyone_wins - df['Кол. побед']
            df['Забрать/дать в деньгах'] = df['Не хватает до 2,5'] * reward_win_uah

            st.dataframe(df, hide_index=True, width='content')

        st.write(calculate_transactions(tournaments))
