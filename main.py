import requests
from database import get_database_connection
import flask
from flask import render_template, redirect, url_for
import time, os
from datetime import datetime as dt, timedelta
from flask import request
from fng_index.CNNFearAndGreedIndex import CNNFearAndGreedIndex
from helper_functions import parse_csv
from constants import (
    DATABASE,
    FG_BUY_THRESHOLD_1,
    FG_BUY_RANGE_1_START,
    FG_BUY_RANGE_1_END,
    FG_BUY_RANGE_2_START,
    FG_BUY_RANGE_2_END,
    MEAN_DAYS,
    EUWAX_MIN_VALUE,
    EUWAX_MAX_VALUE,
    VIX_THRESHOLD,
    SELL_FG_MAX_VALUE,
    SELL_FG_RANGE_START,
    SELL_FG_RANGE_END,
    EUWAX_SELL_THRESHOLD
    )

import json
# import yahoo_fin.stock_info as si

import scrapers

app = flask.Flask(__name__, static_url_path='',
            static_folder='static',
            template_folder='template')

app.config["DEBUG"] = True

def get_stock_rsi_settings():
    db_connection = get_database_connection()
    cursor = db_connection.cursor(dictionary=True)
    sql = f"SELECT * FROM {DATABASE}.settings"
    cursor.execute(sql)
    settings = cursor.fetchall()
    if(not bool(settings)):
        settings = {
            'id': 0,
            'days_period_RSL': 10,
            'moving_average_TSI': 10,
            'reported_days': 100,
            'yahoo_price_data_days': 400,
            'gurufocus_price_data_days': 300,
            'euwax_url': 'https://www.onvista.de/onvista/times+sales/popup/historische-kurse/?notationId=60782956&dateStart=START_DATE&interval=Y5&assetName=EUWAX%20SENTIMENT%20%20AVERAGE%2012M&exchange=Stuttgart',
            'vix_url': 'https://de.investing.com/indices/volatility-s-p-500-historical-data'
        }
    else:
        settings = settings[0]
    db_connection.close()
    return settings


@app.route("/")
def dashboard():
    return render_template(
        'dashboard.html'
    )


@app.route("/import")
def csv_index():
    allow_pull = False
    db_connection = get_database_connection()
    cursor = db_connection.cursor(dictionary=True)
    sql = f"SELECT max(pull_date) as max_pull_date FROM {DATABASE}.pull_data_history"
    cursor.execute(sql)
    last_pulled_date = cursor.fetchall()[0]['max_pull_date']
    if(last_pulled_date == None):
        allow_pull = True
        last_pulled = 'No Data Pulled Yet'
    else:
        allow_pull = last_pulled_date.date() < dt.now().date()
        last_pulled = last_pulled_date.strftime('%d, %b %Y')
    
    sql = f"SELECT * FROM {DATABASE}.datasource"
    cursor.execute(sql)
    datasource_items = cursor.fetchall()
    db_connection.close()
    return render_template(
        "csv.html",
        last_pulled=last_pulled,
        allow_pull=allow_pull,
        datasource_items=datasource_items
    )


# Get the uploaded file
@app.route("/", methods=['POST'])
def upload_files():
    db_connection = get_database_connection()
    cursor = db_connection.cursor()
    # get the uploaded file
    uploaded_file = request.files['file']
    if uploaded_file.filename != '':
        uploads_folder_path = os.path.join(os.path.dirname(__file__), 'uploads')
        if not os.path.exists(uploads_folder_path):
            # Create a new directory because it does not exist 
            os.makedirs(uploads_folder_path)
        file_path = os.path.join(uploads_folder_path, uploaded_file.filename)
        # set the file path
        uploaded_file.save(file_path)
        csv_data = parse_csv(file_path)
        os.remove(file_path)

    wl_name = uploaded_file.filename
    sql = f"INSERT INTO {DATABASE}.watchlist (`name`)"
    sql = sql+" values(%s)"
    val = (wl_name,)
    cursor.execute(sql, val)
    cursor = db_connection.cursor(dictionary=True)
    sql = f"SELECT max(id) as wl_id FROM {DATABASE}.watchlist"
    cursor.execute(sql)
    items = cursor.fetchall()
    wl_id = items[0]['wl_id']

    for r in csv_data:
        sql = f"insert into {DATABASE}.input (`company`, `symbol`, `price`, `date`, `watchlist_id`, `datasource_id`)"
        sql = sql+" values(%s,%s,%s,%s,%s,%s)"
        val = (r['company'],
               r['symbol'] ,
               0,
               dt.now(),
               wl_id,
               int(request.form.get('datasource_id')),
            )
        cursor.execute(sql, val)
    db_connection.commit()

    # Pulling the last pulled date from history table
    allow_pull = False
    db_connection = get_database_connection()
    cursor = db_connection.cursor(dictionary=True)
    sql = f"SELECT max(pull_date) as max_pull_date FROM {DATABASE}.pull_data_history"
    cursor.execute(sql)
    last_pulled_date = cursor.fetchall()[0]['max_pull_date']
    if(last_pulled_date == None):
        allow_pull = True
        last_pulled = 'No Data Pulled Yet'
    else:
        allow_pull = last_pulled_date.date() < dt.now().date()
        last_pulled = last_pulled_date.strftime('%d, %b %Y')

    sql = f"SELECT * FROM {DATABASE}.datasource"
    cursor.execute(sql)
    datasource_items = cursor.fetchall()
    db_connection.close()

    request.files = None
    request.form = None
    return render_template(
        'csv.html',
        csv_records=csv_data,
        last_pulled=last_pulled,
        allow_pull=allow_pull,
        datasource_items=datasource_items
    )


@app.route("/watchlist", methods=['GET', 'POST'])
def watchlist_index():
    if(request.method == 'GET'):
        if('id' in request.args):
            db_connection = get_database_connection()
            cursor = db_connection.cursor()

            # Making Delete query to remove Item from Database
            sql = f"DELETE FROM {DATABASE}.input WHERE watchlist_id={request.args['id']}"
            cursor.execute(sql)
            db_connection.commit() # Transacctional Commit

            # Making Delete query to remove Item from Database
            sql = f"DELETE FROM {DATABASE}.watchlist WHERE id={request.args['id']}"
            cursor.execute(sql)
            db_connection.commit() # Transacctional Commit
            db_connection.close()
            return redirect(url_for('watchlist_index'))
        else:
            top_2_ranks_of_lists = []
            db_connection = get_database_connection()
            cursor = db_connection.cursor(dictionary=True)
            sql = f"SELECT * FROM {DATABASE}.watchlist"
            cursor.execute(sql)
            watchlists = cursor.fetchall()
            sql = '''select * from all_ranks_calculations arc where 
                    date = (select max(date) from all_ranks_calculations arc_max)'''
            cursor.execute(sql)
            top_2_ranked_data = cursor.fetchall()
            wl_ids_of_combinedTop_ranks = {i['watchlist_id'] for i in top_2_ranked_data}
            wl_ids_of_Top_ranks = []
            if(len(wl_ids_of_combinedTop_ranks) > 0):
                wl_ids_of_Top_ranks = wl_ids_of_combinedTop_ranks
                
            else:
                sql = '''select * from ranks_calculations rc where 
                    date = (select max(date) from ranks_calculations rc_max)'''
                cursor.execute(sql)
                top_2_ranked_data = cursor.fetchall()
                wl_ids_of_Top_ranks = {i['watchlist_id'] for i in top_2_ranked_data}

            for wl_id in wl_ids_of_Top_ranks:
                    top_2_of_a_watchlist = list(filter(
                            lambda wl_value: wl_value['watchlist_id'] == wl_id,
                            top_2_ranked_data
                        ))
                    # Filtering unique symbols records
                    top_2_of_a_watchlist = list({v['symbol']:v for v in top_2_of_a_watchlist}.values())
                    top_2_of_a_watchlist.sort(key=lambda x: x['tsi_mean_percentage_rank'], reverse=False)
                    top_2_ranks_of_lists.append(
                        [
                            list(filter(
                                lambda wl_value: wl_value['id'] == wl_id,
                                watchlists
                            ))[0]['name'], enumerate(top_2_of_a_watchlist if len(top_2_of_a_watchlist) < 2 else top_2_of_a_watchlist[0:2])
                        ]
                    )

            
            db_connection.close()
            return render_template(
                "watchlistIndex.html",
                watchlist_records=watchlists,
                top_2_ranks_of_lists=top_2_ranks_of_lists
            )
    elif(request.method == 'POST'):
        db_connection = get_database_connection()
        cursor = db_connection.cursor()
        if('id' in request.form):
            sql = f"UPDATE {DATABASE}.watchlist SET `name`='{request.form.get('name')}' WHERE `id`={request.form.get('id')}"
            cursor.execute(sql)
            db_connection.commit()
            db_connection.close()
            return 'Item updated Successfully'
        else:    
            sql = f"insert into {DATABASE}.watchlist (`name`)"
            sql = sql+" values(%s)"
            val = (request.form.get('name'),)
            cursor.execute(sql, val)
            db_connection.commit()
            db_connection.close()
            return 'Item Added Successfully'

@app.route("/manual", methods=['GET', 'POST'])
def manual_input():
    db_connection = get_database_connection()
    cursor = db_connection.cursor(dictionary=True)
    sql = f"SELECT * FROM {DATABASE}.watchlist"
    cursor.execute(sql)
    watchlist_items = cursor.fetchall()
    sql = f"SELECT * FROM {DATABASE}.datasource"
    cursor.execute(sql)
    datasource_items = cursor.fetchall()
    if(request.method == 'GET'):
        db_connection.close()
        return render_template(
            'manualInput.html',
            datasource_items=datasource_items,
            watchlist_items=watchlist_items,
            message=''
        )
    elif(request.method == 'POST'):
        db_connection = get_database_connection()
        cursor = db_connection.cursor()
        sql = f"insert into {DATABASE}.input (`company`, `symbol`, `price`, `date`, `watchlist_id`, `datasource_id`)"
        sql = sql+" values(%s,%s,%s,%s,%s,%s)"
        val = (request.form.get('company'),
                request.form.get('symbol'),
                None if request.form.get('price').strip() == '' or float(request.form.get('price')) == 0  else float(request.form.get('price')),
                dt.now(),
                int(request.form.get('watchlist_id')),
                None if int(request.form.get('datasource_id')) == 0 else int(request.form.get('datasource_id'))
            )
        cursor.execute(sql, val)
        db_connection.commit()
        db_connection.close()
        return render_template(
            'manualInput.html',
            datasource_items=datasource_items,
            watchlist_items=watchlist_items,
            message='Manual input saved successfully.'
        )


@app.route("/view-watchlist", methods=['GET', 'POST'])
def watchlist_items_index():
    db_connection = get_database_connection()
    cursor = db_connection.cursor(dictionary=True)
    sql = f"SELECT i.id input_id_pk, d.name, i.company, i.symbol, i.date FROM {DATABASE}.input i join datasource d on i.datasource_id = d.id WHERE `watchlist_id`={request.args['watchlist_id']}"
    cursor.execute(sql)
    items = cursor.fetchall()
    for index, i in enumerate(items):
        cursor = db_connection.cursor(dictionary=True)
        sql = f"select * from price_data pd where symbol = '{i['symbol']}' order by `date` desc limit 1"
        cursor.execute(sql)
        closing_price = cursor.fetchall()
        items[index]['close_price'] = None if not bool(closing_price) else closing_price[0]['close_price']
        items[index]['close_date'] = None if not bool(closing_price) else closing_price[0]['date']

    return render_template('watchlistItems.html',
                            wl_name=request.args['watchlist_name'],
                            wl_items=items)


@app.route("/delete-watchlist-item", methods=['GET'])
def watchlist_item_delete():
    db_connection = get_database_connection()
    cursor = db_connection.cursor()

    # Making Delete query to remove Item from Database
    sql = f"DELETE FROM {DATABASE}.input WHERE id={request.args['id']}"
    cursor.execute(sql)
    db_connection.commit() # Transacctional Commit
    db_connection.close()
    return "Watchlist items deleted"


@app.route("/edit-watchlist-item", methods=['GET', 'POST'])
def edit_watchlist_item():
    db_connection = get_database_connection()
    cursor = db_connection.cursor(dictionary=True)
    sql = f"SELECT * FROM {DATABASE}.watchlist"
    cursor.execute(sql)
    watchlist_items = cursor.fetchall()
    sql = f"SELECT * FROM {DATABASE}.datasource"
    cursor.execute(sql)
    datasource_items = cursor.fetchall()
    if(request.method == 'GET'):
        sql = f"SELECT * FROM {DATABASE}.input where id={request.args['id']}"
        cursor.execute(sql)
        watchlist_item_to_edit = cursor.fetchall()[0]
        if(watchlist_item_to_edit['price'] == 0.0):
            cursor = db_connection.cursor(dictionary=True)
            sql = f"select * from price_data pd where symbol = '{watchlist_item_to_edit['symbol']}' order by `date` desc limit 1"
            cursor.execute(sql)
            closing_price = cursor.fetchall()
            if(not bool(closing_price)):
                watchlist_item_to_edit['price'] = 0.0
            else:
                watchlist_item_to_edit['price'] = closing_price[0]['close_price']
        db_connection.close()
        return render_template(
            'editWatchlistItem.html',
            datasource_items=datasource_items,
            watchlist_items=watchlist_items,
            model=watchlist_item_to_edit,
            message=''
        )
    elif(request.method == 'POST'):
        db_connection = get_database_connection()
        cursor = db_connection.cursor()
        sql = f"UPDATE {DATABASE}.input SET `company`='{ request.form.get('company')}', `symbol`='{ request.form.get('symbol')}', `price`={0.0 if request.form.get('price') == '' else request.form.get('price') }, `watchlist_id`={request.form.get('watchlist_id')}, `datasource_id`={request.form.get('datasource_id')} WHERE `id`={request.form.get('id')}"
        cursor.execute(sql)
        db_connection.commit()
        cursor = db_connection.cursor(dictionary=True)
        sql = f"SELECT * FROM {DATABASE}.watchlist where id={int(request.form.get('watchlist_id'))}"
        cursor.execute(sql)
        watchlist = cursor.fetchall()[0]
        db_connection.close()
        return redirect(f'/view-watchlist?watchlist_id={request.form.get("watchlist_id")}&watchlist_name={watchlist["name"]}')


@app.route("/pull-price-data", methods=['GET'])
def pull_price_data():
    settings = get_stock_rsi_settings()
    db_connection = get_database_connection()
    cursor = db_connection.cursor(dictionary=True)
    sql = f"SELECT * FROM {DATABASE}.watchlist"
    cursor.execute(sql)
    watchlists = cursor.fetchall()

    # Deleting all the Gurufocus Price Data to add new latest 300 days data, It
    # would happend everytime at the start of pull_price_data function as per our business logic committed
    cursor = db_connection.cursor(dictionary=True)
    sql = f"DELETE FROM {DATABASE}.price_data WHERE datasource_id={2}" # here 2 id is for gurufocus datasource
    cursor.execute(sql)
    db_connection.commit()

    for wl in watchlists:
        sql = f"SELECT * FROM {DATABASE}.input WHERE `watchlist_id`={wl['id']}"
        cursor.execute(sql)
        inputs = cursor.fetchall()
        for i in inputs:
            if(int(i['datasource_id']) == 1):
                cursor = db_connection.cursor(dictionary=True)
                sql = f"select max(date) as latest_price_date from price_data pd where symbol = '{i['symbol']}'"
                cursor.execute(sql)
                latest_price_data = cursor.fetchall()
                end_date = dt.now() - timedelta(days=1)
                if(not bool(latest_price_data[0]['latest_price_date'])):
                    start_date = end_date - timedelta(days=int(settings['yahoo_price_data_days']))
                else:
                    start_date = latest_price_data[0]['latest_price_date'] + timedelta(days=1)
                try:
                    df = si.get_data(
                        i['symbol'],
                        start_date = "{:02d}/{:02d}/{}".format(start_date.month, start_date.day, start_date.year),
                        end_date = "{:02d}/{:02d}/{}".format(end_date.month, end_date.day, end_date.year)
                    )
                except KeyError as e:
                    if(str(e) == "'timestamp'"):
                        continue
                dates = df.index
                data = df.to_dict('records')
                for index, value in enumerate(data):
                    sql = f"INSERT INTO {DATABASE}.price_data (`symbol`, `close_price`, `date`, `datasource_id`)"
                    sql = sql+" values(%s, %s, %s, %s)"
                    val = (
                        i['symbol'],
                        value['close'],
                        str(dates[index]),
                        1
                    )
                    cursor.execute(sql, val)
                db_connection.commit()
            elif(int(i['datasource_id']) == 2):
                response = requests.get(f"https://api.gurufocus.com/public/user/{GURUFOCUS_TOKEN}/stock/{i['symbol']}/price")
                gurufocus_price_data = json.loads(response.text)
                if(len(gurufocus_price_data) >= int(settings['gurufocus_price_data_days'])):
                    cursor = db_connection.cursor()
                    for gurufocus_price in gurufocus_price_data[len(gurufocus_price_data) - int(settings['gurufocus_price_data_days']) : ]:
                        sql = f"INSERT INTO {DATABASE}.price_data (`symbol`, `close_price`, `date`, `datasource_id`)"
                        sql = sql+" values(%s, %s, %s, %s)"
                        val = (
                            i['symbol'],
                            gurufocus_price[1],
                            dt(
                                int(gurufocus_price[0].split('-')[2]), # year on 2 index
                                int(gurufocus_price[0].split('-')[0]), # month on 0 index
                                int(gurufocus_price[0].split('-')[1]) # day on 1 index
                            ),
                            2
                        )
                        cursor.execute(sql, val)
                    db_connection.commit()
                time.sleep(60)

    cursor = db_connection.cursor()
    sql = f"INSERT INTO {DATABASE}.pull_data_history (`pull_date`)"
    sql = sql+" values(%s)"
    val = (dt.now(),)
    cursor.execute(sql, val)
    db_connection.commit()
    db_connection.close()
    return 'Data pull completed successfully'


@app.route('/view-pull-data-history', methods=['GET'])
def view_pull_data_history():
    db_connection = get_database_connection()
    cursor = db_connection.cursor(dictionary=True)
    sql = f"SELECT * FROM {DATABASE}.pull_data_history"
    cursor.execute(sql)
    pulled_data_histories = cursor.fetchall()
    db_connection.close()
    return render_template(
        'pulledPriceDataHistory.html',
        pulled_data_histories=pulled_data_histories
    )


@app.route('/edit-settings', methods=['GET', 'POST'])
def edit_settings():
    message = ''
    model = []
    if(request.method == 'GET'):
        model = get_stock_rsi_settings()
    elif(request.method == 'POST'):
        db_connection = get_database_connection()
        cursor = db_connection.cursor(dictionary=True)
        if(int(request.form.get('id')) == 0):
            sql = f"INSERT INTO {DATABASE}.settings (`days_period_RSL`, `moving_average_TSI`, `reported_days`, `yahoo_price_data_days`, `gurufocus_price_data_days`, `euwax_url`, `vix_url`)"
            sql = sql + " values(%s, %s, %s, %s, %s, %s, %s)"
            val = (
                int(request.form.get('days_period_RSL')),
                int(request.form.get('moving_average_TSI')),
                int(request.form.get('reported_days')),
                int(request.form.get('yahoo_price_data_days')),
                int(request.form.get('gurufocus_price_data_days')),
                request.form.get('euwax_url'),
                request.form.get('vix_url'),
            )
            cursor.execute(sql, val)
        else:
            sql = f"UPDATE {DATABASE}.settings SET `euwax_url`='{request.form.get('euwax_url')}', \
                `vix_url`='{request.form.get('vix_url')}',\
                 `days_period_RSL`={request.form.get('days_period_RSL')},\
                 `moving_average_TSI`={request.form.get('moving_average_TSI')}, `reported_days`=\
                     {request.form.get('reported_days')}, `yahoo_price_data_days`=\
                         {request.form.get('yahoo_price_data_days')}, `gurufocus_price_data_days`=\
                             {request.form.get('gurufocus_price_data_days')} WHERE `id`=\
                                 {request.form.get('id')}"
            cursor.execute(sql)
        db_connection.commit()
        db_connection.close()
        message='Settings Updated'
        model = get_stock_rsi_settings()
    return render_template('settings.html', model=model, message=message)


@app.route('/calculate-stock-rsi', methods=['POST'])
def calculate_stock_rsi():
    settings = get_stock_rsi_settings()
    db_connection = get_database_connection()
    cursor = db_connection.cursor(dictionary=True)
    sql = f"delete from `ranks_calculations`"
    cursor.execute(sql)
    db_connection.commit()
    if(request.form.get('selectedWLs') == 'all'):
        sql = f"SELECT * FROM {DATABASE}.watchlist"
    else:
        sql = f"SELECT * FROM {DATABASE}.watchlist where id in ({request.form.get('selectedWLs')})"
    cursor.execute(sql)
    watchlists = cursor.fetchall()
    calculated_list_of_tickers_of_all_watchlists = []
    rsl_days_dates = []
    for wl in watchlists: # Iterating all watchlists
        sql = f"SELECT * FROM {DATABASE}.input WHERE `watchlist_id`={wl['id']}"
        cursor.execute(sql)
        wl_items = cursor.fetchall()
        for wli in wl_items: # Iterating all items of watchlist
            sql = f"select * from price_data pd where symbol  = '{wli['symbol']}'" # Getting all existing price data of the symbol/Ticker
            cursor.execute(sql)
            all_price_data = cursor.fetchall()
            all_price_data_of_rsl_days = all_price_data[(len(all_price_data) - (int(settings['reported_days']) + int(settings['days_period_RSL']) + int(settings['moving_average_TSI']))):]
            # Step 1 Calculation
            for day_price_record in all_price_data_of_rsl_days:
                if(len(rsl_days_dates) != (int(settings['reported_days']) + int(settings['days_period_RSL']) + int(settings['moving_average_TSI']))):
                    rsl_days_dates.append(day_price_record['date'])
                RSL_period_data = all_price_data[(all_price_data.index(day_price_record) - int(settings['days_period_RSL'])) - 1: all_price_data.index(day_price_record) - 1]
                sum_of_previous_days_prices = 0.00
                for day_data in RSL_period_data:
                    sum_of_previous_days_prices = sum_of_previous_days_prices + float(day_data['close_price'])
                # Finding Average now
                avg_of_previous_days_prices = sum_of_previous_days_prices/len(RSL_period_data)
                calculated_list_of_tickers_of_all_watchlists.append(
                    {
                        'symbol': day_price_record['symbol'],
                        'value': float(float(day_price_record['close_price'])/avg_of_previous_days_prices),
                        'date': day_price_record['date'],
                        'watchlist_id': wl['id']
                    }
                )
    for wl in watchlists:
        rsl_rank_calculations = []
        for rsl_date in rsl_days_dates:
            filtered_on_day = list(filter(
                        lambda day_value: day_value['date'] == rsl_date and day_value['watchlist_id'] == wl['id'],
                        calculated_list_of_tickers_of_all_watchlists
                    ))
            if(len(filtered_on_day) > 1):
                filtered_on_day.sort(key=lambda x: x['value'], reverse=True)

                # Adding step 1 calculations in database
                for index, item in enumerate(filtered_on_day):
                    rsl_rank_calculations.append(
                        {
                            'symbol': item['symbol'],
                            'value': float(item['value']),
                            'rsl_rank': index+1,
                            'watchlist_id': int(item['watchlist_id']),
                            'date': item['date'],
                            'rsl_rank_percentage': round(100-((100/(len(filtered_on_day)-1))*(index)))
                        }
                    )

                    sql = f"INSERT INTO {DATABASE}.ranks_calculations (`symbol`, `rsl_days_value`, `rank_rsl_days_value`, `watchlist_id`, `date`, `rank_rsl_days_percentage`)"
                    sql = sql + " values(%s, %s, %s, %s, %s, %s)"
                    val = (
                        item['symbol'],
                        float(item['value']),
                        index+1,
                        int(item['watchlist_id']),
                        item['date'],
                        round(100-((100/(len(filtered_on_day)-1))*(index))),
                    )
                    cursor.execute(sql, val)
                db_connection.commit()


    for wl in watchlists: # Iterating all watchlists for tsi
        sql = f"SELECT * FROM {DATABASE}.input WHERE `watchlist_id`={wl['id']}"
        cursor.execute(sql)
        wl_items = cursor.fetchall()
        for wli in wl_items:
            for rsl_date in rsl_days_dates[len(rsl_days_dates)-((int(settings['reported_days']) + int(settings['moving_average_TSI']))):]:
                tsi_days_sum = 0
                sql = f"select * from ranks_calculations rc where symbol = '{wli['symbol']}' and `date`='{rsl_date.strftime('%Y-%m-%d %H:%M:%S')}'"
                cursor.execute(sql)
                day_of_rsl_rank = cursor.fetchall()[0]
                sql = f"select * from ranks_calculations where symbol = '{wli['symbol']}' and date < date('{rsl_date.strftime('%Y-%m-%d %H:%M:%S')}') order by date desc limit {int(settings['moving_average_TSI'])}"
                cursor.execute(sql)
                tsi_days_data = cursor.fetchall()
                for i in tsi_days_data:
                    tsi_days_sum = tsi_days_sum + i['rank_rsl_days_percentage']
                tsi_mean_percentage = round(tsi_days_sum/len(tsi_days_data))
                print(tsi_mean_percentage)
                sql = f"UPDATE {DATABASE}.ranks_calculations SET `tsi_mean_percentage`={tsi_mean_percentage} WHERE `id`={day_of_rsl_rank['id']}"
                cursor.execute(sql)
                db_connection.commit()


    
    for rsl_date in rsl_days_dates[len(rsl_days_dates)-((int(settings['reported_days']) + int(settings['moving_average_TSI']))):]:
        for wl in watchlists:
            sql = f"select * from ranks_calculations rc WHERE watchlist_id={wl['id']} and `date`='{rsl_date.strftime('%Y-%m-%d %H:%M:%S')}' order by tsi_mean_percentage desc"
            cursor.execute(sql)
            tsi_mean_percentages_of_day = cursor.fetchall()
            for index, item in enumerate(tsi_mean_percentages_of_day):
                sql = f"UPDATE {DATABASE}.ranks_calculations SET `tsi_mean_percentage_rank`={index+1} WHERE `id`={item['id']}"
                cursor.execute(sql)
            db_connection.commit()



    db_connection.close()
    return 'Calculations and Ranking has been Completed'


@app.route('/calculate-combined-stock-rsi', methods=['POST'])
def calculate_all_stock_rsi():
    settings = get_stock_rsi_settings()
    db_connection = get_database_connection()
    cursor = db_connection.cursor(dictionary=True)
    sql = f"delete from `all_ranks_calculations`"
    cursor.execute(sql)
    db_connection.commit()
    if(',' in request.form.get('selectedWLs')):
        sql = f"SELECT * FROM {DATABASE}.watchlist where id in ({request.form.get('selectedWLs')})"
    else:
        sql = f"SELECT * FROM {DATABASE}.watchlist"

    cursor.execute(sql)
    watchlists = cursor.fetchall()
    calculated_list_of_tickers_of_all_watchlists = []
    rsl_days_dates = []
    for wl in watchlists: # Iterating all watchlists
        sql = f"SELECT * FROM {DATABASE}.input WHERE `watchlist_id`={wl['id']}"
        cursor.execute(sql)
        wl_items = cursor.fetchall()
        for wli in wl_items: # Iterating all items of watchlist
            sql = f"select * from price_data pd where symbol  = '{wli['symbol']}'" # Getting all existing price data of the symbol/Ticker
            cursor.execute(sql)
            all_price_data = cursor.fetchall()
            all_price_data_of_rsl_days = all_price_data[
                (len(all_price_data) - (int(settings['reported_days']) + int(settings['days_period_RSL']) + int(settings['moving_average_TSI'])))
                :]
            # Step 1 Calculation
            for day_price_record in all_price_data_of_rsl_days:
                if(len(rsl_days_dates) != (int(settings['reported_days']) + int(settings['days_period_RSL']) + int(settings['moving_average_TSI']))):
                    rsl_days_dates.append(day_price_record['date'])
                RSL_period_data = all_price_data[(all_price_data.index(day_price_record) - int(settings['days_period_RSL'])) - 1: all_price_data.index(day_price_record) - 1]
                sum_of_previous_days_prices = 0.00
                for day_data in RSL_period_data:
                    sum_of_previous_days_prices = sum_of_previous_days_prices + float(day_data['close_price'])
                # Finding Average now
                avg_of_previous_days_prices = sum_of_previous_days_prices/len(RSL_period_data)
                calculated_list_of_tickers_of_all_watchlists.append(
                    {
                        'symbol': day_price_record['symbol'],
                        'value': float(float(day_price_record['close_price'])/avg_of_previous_days_prices),
                        'date': day_price_record['date'],
                        'watchlist_id': wl['id']
                    }
                )

    rsl_rank_calculations = []
    for rsl_date in rsl_days_dates:
        filtered_on_day = list(filter(
                    lambda day_value: day_value['date'] == rsl_date,
                    calculated_list_of_tickers_of_all_watchlists
                ))
        if(len(filtered_on_day) > 1):
            filtered_on_day.sort(key=lambda x: x['value'], reverse=True)

            # Adding step 1 calculations in database
            for index, item in enumerate(filtered_on_day):
                rsl_rank_calculations.append(
                    {
                        'symbol': item['symbol'],
                        'value': float(item['value']),
                        'rsl_rank': index+1,
                        'watchlist_id': int(item['watchlist_id']),
                        'date': item['date'],
                        'rsl_rank_percentage': round(100-((100/(len(filtered_on_day)-1))*(index)))
                    }
                )

                sql = f"INSERT INTO {DATABASE}.all_ranks_calculations (`symbol`, `rsl_days_value`, `rank_rsl_days_value`, `watchlist_id`, `date`, `rank_rsl_days_percentage`)"
                sql = sql + " values(%s, %s, %s, %s, %s, %s)"
                val = (
                    item['symbol'],
                    float(item['value']),
                    index+1,
                    int(item['watchlist_id']),
                    item['date'],
                    round(100-((100/(len(filtered_on_day)-1))*(index))),
                )
                cursor.execute(sql, val)
            db_connection.commit()


    for wl in watchlists: # Iterating all watchlists for tsi
        sql = f"SELECT * FROM {DATABASE}.input WHERE `watchlist_id`={wl['id']}"
        cursor.execute(sql)
        wl_items = cursor.fetchall()
        for wli in wl_items:
            for rsl_date in rsl_days_dates[
                len(rsl_days_dates)-(int(settings['reported_days']) + int(settings['moving_average_TSI']))
                :]:
                tsi_days_sum = 0
                sql = f"select * from all_ranks_calculations rc where symbol = '{wli['symbol']}' and `date`='{rsl_date.strftime('%Y-%m-%d %H:%M:%S')}'"
                cursor.execute(sql)
                day_of_rsl_rank = cursor.fetchall()[0]
                sql = f"select * from all_ranks_calculations where symbol = '{wli['symbol']}' and date < date('{rsl_date.strftime('%Y-%m-%d %H:%M:%S')}') order by date desc limit {int(settings['moving_average_TSI'])}"
                cursor.execute(sql)
                tsi_days_data = cursor.fetchall()
                for i in tsi_days_data:
                    tsi_days_sum = tsi_days_sum + i['rank_rsl_days_percentage']
                tsi_mean_percentage = round(tsi_days_sum/len(tsi_days_data))
                print(tsi_mean_percentage)
                sql = f"UPDATE {DATABASE}.all_ranks_calculations SET `tsi_mean_percentage`={tsi_mean_percentage} WHERE `id`={day_of_rsl_rank['id']}"
                cursor.execute(sql)
                db_connection.commit()

    for rsl_date in rsl_days_dates[len(rsl_days_dates)-(int(settings['reported_days']) + int(settings['moving_average_TSI'])):]:
        sql = f"select * from all_ranks_calculations rc WHERE `date`='{rsl_date.strftime('%Y-%m-%d %H:%M:%S')}' order by tsi_mean_percentage desc"
        cursor.execute(sql)
        tsi_mean_percentages_of_day = cursor.fetchall()
        for index, item in enumerate(tsi_mean_percentages_of_day):
            sql = f"UPDATE {DATABASE}.all_ranks_calculations SET `tsi_mean_percentage_rank`={index+1} WHERE `id`={item['id']}"
            cursor.execute(sql)
        db_connection.commit()

    db_connection.close()
    return 'Calculations and Ranking has been Completed for all'



@app.route("/view-calculations", methods=['GET'])
def view_calculations():
    db_connection = get_database_connection()
    cursor = db_connection.cursor(dictionary=True)
    sql = f"select * from ranks_calculations rc where watchlist_id = {request.args.get('wl_id')} and tsi_mean_percentage is not null order by date desc"
    cursor.execute(sql)
    tsi_calculations = cursor.fetchall()
    sql = f"select max(date) max_date from ranks_calculations"
    cursor.execute(sql)
    max_date = cursor.fetchall()[0]
    return render_template(
        'tsiCalculations.html',
        tsi_calculations=enumerate(tsi_calculations),
        watchlist_name=request.args.get('watchlist_name'),
        max_ranking_date=max_date['max_date']
    )


@app.route("/view-all-calculations", methods=['GET'])
def view_all_calculations():
    db_connection = get_database_connection()
    cursor = db_connection.cursor(dictionary=True)
    sql = f"select * from all_ranks_calculations rc where tsi_mean_percentage is not null order by date desc"
    cursor.execute(sql)
    tsi_calculations = cursor.fetchall()
    sql = f"select max(date) max_date from all_ranks_calculations"
    cursor.execute(sql)
    max_date = cursor.fetchall()[0]
    return render_template(
        'tsiAllCalculations.html',
        tsi_calculations=enumerate(tsi_calculations),
        max_ranking_date=max_date['max_date']
    )


@app.route("/api/v1/all-history-data", methods=['GET'])
def get_all_history_data():
    # Upudating EUWAX and VIX data
    scrapers.pull_euwax_history_data()
    scrapers.pull_vix_data()

    data = {}
    db_connection = get_database_connection()
    cursor = db_connection.cursor(dictionary=True)
    sixth_previous_month_date = dt.now() - timedelta(days=185)
    sql = f"SELECT `value`, `created_on` from {DATABASE}.euwax WHERE created_on > '{str(sixth_previous_month_date.date())}' order by created_on ASC"
    cursor.execute(sql)
    euwax_data = cursor.fetchall()
    
    x_y_axis_data = []
    for i in euwax_data:
        x_y_axis_data.append(
            {
                "x": i['created_on'].strftime('%d, %b %Y'),
                "y": i['value']
            }
        )
    data['euwax'] = x_y_axis_data
    data['euwax_meter'] = x_y_axis_data[-1] if len(euwax_data) > 0 else None

    sql = f"SELECT `value`, `created_on` from {DATABASE}.vix WHERE created_on > '{str(sixth_previous_month_date.date())}' order by created_on ASC"
    cursor.execute(sql)
    de_inesting_data = cursor.fetchall()
    x_y_axis_data = []
    for i in de_inesting_data:
        x_y_axis_data.append(
            {
                "x": i['created_on'].strftime('%d, %b %Y'),
                "y": i['value']
            }
        )
    data['vix'] = x_y_axis_data
    data['vix_meter'] = x_y_axis_data[-1] if len(de_inesting_data) > 0 else None

    sql = f"SELECT `current_value`, `created_on` from {DATABASE}.fear_greed_index WHERE created_on > '{str(sixth_previous_month_date.date())}' order by created_on ASC"
    cursor.execute(sql)
    fear_greed_data = cursor.fetchall()
    x_y_axis_data = []
    for i in fear_greed_data:
        x_y_axis_data.append(
            {
                "x": i['created_on'].strftime('%d, %b %Y'),
                "y": i['current_value']
            }
        )
    data['fear_and_greed'] = x_y_axis_data
    data['fear_and_greed_meter'] = x_y_axis_data[0]
    cnn_fg = CNNFearAndGreedIndex()
    data['fg_index_values'] = []
    for fg in cnn_fg.index_summary.split('\n'):
        data['fg_index_values'].append(
            {
                'day': fg.strip().split(':')[0],
                'value': fg.strip().split(': ')[1].split(' (')[0],
                'category': fg.strip().split(' (')[1].split(')')[0]
            }
        )
    data['last_updated_on'] = cnn_fg.get_indicators_report().split('[Updated ')[-1].split(']')[0]
    # Measuring SELL and BUY lights
    data['is_buy'] = False
    data['is_sell'] = False
    #Loop through the array to calculate sum of elements
    fg_sum_last_x_days = 0
    for i in range(1, 1 + MEAN_DAYS):
        fg_sum_last_x_days = fg_sum_last_x_days + data['fear_and_greed'][i]['y']
    
    #Loop through the array to calculate sum of elements
    euwax_sum_last_x_days = 0  
    for i in range(-2, -2 - MEAN_DAYS, -1):
        euwax_sum_last_x_days = euwax_sum_last_x_days + data['euwax'][i]['y']

    last_3_days_fg_avg = fg_sum_last_x_days/MEAN_DAYS
    last_3_days_euwax_avg = euwax_sum_last_x_days/MEAN_DAYS
    buy_rule_1 = data['fear_and_greed'][0]['y'] < FG_BUY_THRESHOLD_1
    buy_rule_2 = data['fear_and_greed'][0]['y'] <= FG_BUY_RANGE_1_END and data['fear_and_greed'][0]['y'] >= FG_BUY_RANGE_1_START
    buy_rule_3 = data['fear_and_greed'][0]['y'] <= FG_BUY_RANGE_2_END and data['fear_and_greed'][0]['y'] >= FG_BUY_RANGE_2_START and data['fear_and_greed'][0]['y'] > last_3_days_fg_avg
    buy_rule_4 = data['euwax'][-1]['y'] <= EUWAX_MIN_VALUE
    buy_rule_5 = data['euwax'][-1]['y'] >= EUWAX_MAX_VALUE and data['euwax'][-1]['y'] < last_3_days_euwax_avg
    buy_rule_6 = data['vix'][-1]['y'] < VIX_THRESHOLD
    
    # Applying Buy Rules
    if(buy_rule_1 or buy_rule_2 or buy_rule_3):
        if(buy_rule_4 or buy_rule_5):
            if(buy_rule_6):
                data['is_buy'] = True

    
    sell_rule_1 = data['fear_and_greed'][0]['y'] > SELL_FG_MAX_VALUE
    sell_rule_2 = data['fear_and_greed'][0]['y'] <= SELL_FG_RANGE_END and data['fear_and_greed'][0]['y'] >= SELL_FG_RANGE_START and data['fear_and_greed'][0]['y'] <= last_3_days_fg_avg
    sell_rule_3 = data['euwax'][-1]['y'] >= EUWAX_SELL_THRESHOLD and data['euwax'][-1]['y'] > last_3_days_euwax_avg
    sell_rule_4 = data['vix'][-1]['y'] >= VIX_THRESHOLD
    if(sell_rule_1 or sell_rule_2 or sell_rule_3 or sell_rule_4):
        data['is_sell'] = True

    db_connection.close()
    return json.dumps(data)




if __name__ == '__main__':
    app.run(host="localhost", port=8000, debug=True)
