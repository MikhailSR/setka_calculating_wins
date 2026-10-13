import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs

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
                    f"{d_name} {d_amt:.0f} грн -> {c_name}")
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
                f"{d_name} {amount:.0f} грн -> {c_name}")

            debtors[d_name] -= amount
            creditors[c_name] -= amount

            if creditors[c_name] == 0:
                del creditors[c_name]

    return transactions


st.title("SETKA: расчёт метрик")
col1, col2 = st.columns(2)

url1 = col1.text_input("Ссылка на страницу турнира 1")
url2 = col1.text_input("Ссылка на страницу турнира 2")
url3 = col1.text_input("Ссылка на страницу турнира 3")
url4 = col1.text_input("Ссылка на страницу турнира 4")
url5 = col1.text_input("Ссылка на страницу турнира 5")

reward_win_uah = col2.number_input('Стоимость одной победы', value=100, step=50)
everyone_wins = 2.5

if st.button("Посчитать", type="primary"):
    urls = [url1, url2, url3, url4, url5]
    valid_urls = [url for url in urls if url.strip() != ""]  # <--- ДОБАВЛЕНО: фильтруем пустые

    if not valid_urls:
        st.warning("Турниры не найдены. Введите хотя бы одну ссылку.")
    else:
        all_dfs = []  # Сюда будем складывать все таблицы для финального расчета

        # === ИЗМЕНЕНО: Теперь мы идем циклом по ссылкам, чтобы знать, откуда какая таблица ===
        for url in valid_urls:
            try:
                # 1. Загружаем данные
                df = load_tournament(url)

                # 2. Достаем дату из ссылки (например, ?date=2026-09-30)
                parsed_url = urlparse(url)
                query_params = parse_qs(parsed_url.query)
                tournament_date = query_params.get('date', ['Без даты'])[0]

                # 3. Выводим заголовок с датой перед таблицей
                st.subheader(f"Турнир: {tournament_date}")

                # Расчет и добавление новых столбцов
                target_cols = ['_diag', 'vs_1', 'vs_2', 'vs_3', 'vs_4', 'vs_5']
                df['Кол. побед'] = sum(df[col].str.startswith('3', na=False)
                                       for col in target_cols if col in df.columns)  # Защита, если столбца нет
                df['Не хватает до 2,5'] = everyone_wins - df['Кол. побед']
                df['Забрать/дать в деньгах'] = df['Не хватает до 2,5'] * reward_win_uah

                # Выводим таблицу
                st.dataframe(df, hide_index=True, width='content')

                # Выводим расчет ТОЛЬКО для этого турнира
                st.write(calculate_transactions([df]))

                # Сохраняем в общий список для итогового расчета
                all_dfs.append(df)

            except Exception as e:
                st.error(f"Не удалось загрузить страницу: {url}")
                st.code(str(e))

        # === ИЗМЕНЕНО: Выводим общий итог в самом конце ===
        if all_dfs:
            st.divider()
            st.subheader("Итоговый расчет по ВСЕМ турнирам:")
            st.write(calculate_transactions(all_dfs))
