from flask import request
from constants import DATABASE
from database import get_database_connection
from bs4 import BeautifulSoup
# import matplotlib.pyplot as plt

from datetime import timedelta, datetime as dt
from requests import get


import unittest
import time
from selenium import webdriver
from selenium.webdriver.support.select import Select
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from fng_index.CNNFearAndGreedIndex import CNNFearAndGreedIndex

from main import get_stock_rsi_settings



# # plot Fear and Greed charts
# fig = plt.figure(figsize=(20, 7))
# cnn_fg.plot_all_charts(fig)
# plt.show()



def pull_fear_and_gread_index():
    db_connection = get_database_connection()
    cursor = db_connection.cursor(dictionary=True)
    cnn_fg = CNNFearAndGreedIndex()
    close_value = int(cnn_fg.index_summary.split('\n')[0].strip().split(': ')[1].split(' (')[0])

    # Checking if value already exist for current day
    sql = f"SELECT * FROM {DATABASE}.fear_greed_index WHERE created_on='{str(dt.now().date())}'"
    cursor.execute(sql)
    values_of_current_day = cursor.fetchall()
    if(len(values_of_current_day) > 0 and values_of_current_day[0]['current_value'] != close_value):
        sql = f"UPDATE {DATABASE}.fear_greed_index SET current_value={close_value}, updated_on='{str(dt.now().date())}', updated_on_datetime='{str(dt.now())}' WHERE id={values_of_current_day[0]['id']}"
        cursor.execute(sql)
        db_connection.commit()
    elif(len(values_of_current_day) == 0):
        sql = f"insert into {DATABASE}.fear_greed_index (`current_value`, `created_on`, `created_on_datetime`)"
        sql = sql+" values(%s,%s,%s)"
        val = (close_value,
                dt.now().date(),
                dt.now(),
            )
        cursor.execute(sql, val)
        db_connection.commit()

    db_connection.close()

    return 'Fear & Greed date scrapped successfully.'

def pull_euwax_history_data():
    try:
        settings = get_stock_rsi_settings()
        if('START_DATE' in settings['euwax_url']):
            start_from_date = ''
            print('Scrapping EUWAX data ...')
            db_connection = get_database_connection()
            cursor = db_connection.cursor(dictionary=True)
            sql = f"SELECT MAX(created_on) last_crawled_on FROM {DATABASE}.euwax"
            cursor.execute(sql)
            last_crawled_on = cursor.fetchall()
            last_crawled_on = last_crawled_on[0]['last_crawled_on']
            if(last_crawled_on == None):
                one_year_old_date = dt.now() - timedelta(days=364)
                start_from_date = f'{one_year_old_date.day}.{one_year_old_date.month}.{one_year_old_date.year}'
            else:
                if(last_crawled_on.date() >= dt.now().date()):
                    print( 'VIX data is already up tp date')
                    return
                latest_start_date = last_crawled_on + timedelta(days=1)
                start_from_date = f'{latest_start_date.day}.{latest_start_date.month}.{latest_start_date.year}'
            euwax_history_url = settings['euwax_url'].strip().replace('START_DATE', start_from_date)
            response = get(euwax_history_url)
            html_soup = BeautifulSoup(response.text, 'html.parser')
            table_body = html_soup.find('tbody')
            if(table_body is not None):
                rows = table_body.find_all('tr')
                for row in rows:
                    cols=row.find_all('td')
                    cols=[x.text.strip() for x in cols]
                    sql = f"insert into {DATABASE}.euwax (`value`, `created_on`)"
                    sql = sql+" values(%s,%s)"
                    date = None
                    if('.' in cols[0]): # in . format, Day.Month.Year
                        date = dt(
                            int(cols[0].split('.')[2]),
                            int(cols[0].split('.')[1]),
                            int(cols[0].split('.')[0]),
                        )
                    elif('/' in cols[0]): # in / format, Month.Day.Year
                        date = dt(
                            int(cols[0].split('/')[2]),
                            int(cols[0].split('/')[0]),
                            int(cols[0].split('/')[1])
                        )
                    val = (float(cols[1].replace(',', '.')), date,)
                    cursor.execute(sql, val)
                db_connection.commit()
                db_connection.close()
                print(f'{len(rows)} Day(s) EUWAX Data Scrapped successfully!')
            else:
                print('No data available to scrap')
        else:
            print('Could not scrap EUWAX, START_DATE placeholder does not exist in the url')
    except Exception as e:
        print(e)

def pull_vix_data():
    settings = get_stock_rsi_settings()
    if(settings['vix_url'] is not None and settings['vix_url'].strip() != ''):
        start_from_date = ''
        print('Scrapping VIX data ...')
        db_connection = get_database_connection()
        cursor = db_connection.cursor(dictionary=True)
        sql = f"SELECT MAX(created_on) last_crawled_on FROM {DATABASE}.vix"
        cursor.execute(sql)
        last_crawled_on = cursor.fetchall()
        last_crawled_on = last_crawled_on[0]['last_crawled_on']
        if(last_crawled_on == None):
            one_year_old_date = dt.now() - timedelta(days=364)
            start_from_date = f'{one_year_old_date.day}/{one_year_old_date.month}/{one_year_old_date.year}'
        else:
            if(last_crawled_on.date() >= dt.now().date()):
                print('VIX data is already up tp date')
                return
            latest_start_date = last_crawled_on + timedelta(days=1)
            if(latest_start_date.date() == dt.now().date()):
                print('VIX data is already up tp date')
                return
            start_from_date = f'{latest_start_date.day}/{latest_start_date.month}/{latest_start_date.year}'
        vix_url = settings['vix_url']
        options = webdriver.ChromeOptions()
        options.add_argument('--ignore-certificate-errors-spki-list')
        options.add_argument('--ignore-ssl-errors')
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), chrome_options=options)        driver.get(vix_url)
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.ID, "widgetFieldDateRange")))
        driver.find_element_by_xpath("//*[@id='widgetFieldDateRange']").click()
        start_date_element = driver.find_element_by_xpath("//*[@id='startDate']")
        start_date_element.clear()
        start_date_element.send_keys(start_from_date)
        search_btn = driver.find_element_by_xpath("//*[@id='applyBtn']")
        search_btn.click()
        WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.ID, "curr_table")))
        records = driver.find_elements_by_xpath("//*[@id='curr_table']/tbody/tr")
        if(len(records[0].find_elements_by_tag_name('td')) == 1):
            print(f'No record could found so far for VIX, after {start_from_date}')
            return
        # Scrapping values from table
        db_connection = get_database_connection()
        cursor = db_connection.cursor(dictionary=True)
        for record in records:
            str_date = record.find_elements_by_tag_name('td')[0].text.strip()
            value = record.find_elements_by_tag_name('td')[1].text.strip()
            sql = f"insert into {DATABASE}.vix (`value`, `created_on`)"
            sql = sql+" values(%s,%s)"
            date = None
            if('.' in str_date): # in . format, Day.Month.Year
                date = dt(
                    int(str_date.split('.')[2]),
                    int(str_date.split('.')[1]),
                    int(str_date.split('.')[0]),
                )
            elif('/' in str_date): # in / format, Month.Day.Year
                date = dt(
                    int(str_date.split('/')[2]),
                    int(str_date.split('/')[0]),
                    int(str_date.split('/')[1])
                )
            val = (float(value.replace(',', '.')), date,)
            cursor.execute(sql, val)
        db_connection.commit()
        db_connection.close()
        print(f'{len(records)} Day(s) VIX Data Scrapped successfully!')
    else:
        print('Could not scrap VIX, URL for VIX is not provided.')
