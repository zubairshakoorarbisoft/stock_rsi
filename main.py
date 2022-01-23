from email import message
from statistics import mode
import requests
from database import get_database_connection
import flask
from flask import render_template, redirect, url_for
import time, os
from datetime import datetime as dt, timedelta
from flask import request
from helper_functions import parse_csv
from constants import DATABASE, GURUFOCUS_TOKEN

import json
import yahoo_fin.stock_info as si


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
            'days_period_RSL': 130,
            'moving_average_TSI': 29,
            'reported_days': 100,
            'yahoo_price_data_days': 300,
            'gurufocus_price_data_days': 300
        }
    else:
        settings = settings[0]
    db_connection.close()
    return settings


@app.route("/")
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
            db_connection = get_database_connection()
            cursor = db_connection.cursor(dictionary=True)
            sql = f"SELECT * FROM {DATABASE}.watchlist"
            cursor.execute(sql)
            items = cursor.fetchall()
            sql = '''select * from all_ranks_calculations arc where date = (select max(date) from 
                all_ranks_calculations arc) order by tsi_mean_percentage desc'''
            cursor.execute(sql)
            top_2_ranked_data = cursor.fetchall()
            top_2_ranked_data = list({v['symbol']:v for v in top_2_ranked_data}.values())
            db_connection.close()
            return render_template(
                "watchlistIndex.html",
                watchlist_records=items,
                top_2_ranked_data=top_2_ranked_data
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
            sql = f"INSERT INTO {DATABASE}.settings (`days_period_RSL`, `moving_average_TSI`, `reported_days`, `yahoo_price_data_days`, `gurufocus_price_data_days`)"
            sql = sql + " values(%s, %s, %s, %s, %s)"
            val = (
                int(request.form.get('days_period_RSL')),
                int(request.form.get('moving_average_TSI')),
                int(request.form.get('reported_days')),
                int(request.form.get('yahoo_price_data_days')),
                int(request.form.get('gurufocus_price_data_days')),
            )
            cursor.execute(sql, val)
        else:
            sql = f"UPDATE {DATABASE}.settings SET `days_period_RSL`={request.form.get('days_period_RSL')}, `moving_average_TSI`={request.form.get('moving_average_TSI')}, `reported_days`={request.form.get('reported_days')}, `yahoo_price_data_days`={request.form.get('yahoo_price_data_days')}, `gurufocus_price_data_days`={request.form.get('gurufocus_price_data_days')} WHERE `id`={request.form.get('id')}"
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
            all_price_data_of_rsl_days = all_price_data[(len(all_price_data) - int(settings['days_period_RSL'])):]
            # Step 1 Calculation
            for day_price_record in all_price_data_of_rsl_days:
                if(len(rsl_days_dates) != int(settings['days_period_RSL'])):
                    rsl_days_dates.append(day_price_record['date'])
                RSL_period_data = all_price_data[(all_price_data.index(day_price_record) - int(settings['days_period_RSL'])) : all_price_data.index(day_price_record) - 1]
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


    for wl in watchlists: # Iterating all watchlists
        sql = f"SELECT * FROM {DATABASE}.input WHERE `watchlist_id`={wl['id']}"
        cursor.execute(sql)
        wl_items = cursor.fetchall()
        for wli in wl_items:
            for rsl_date in rsl_days_dates[len(rsl_days_dates)-int(settings['reported_days']):]:
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


    # Ranking TSI Percentages
    # for rsl_date in rsl_days_dates[len(rsl_days_dates)-int(settings['reported_days']):]:
    #     sql = f"select * from ranks_calculations rc WHERE `date`='{rsl_date.strftime('%Y-%m-%d %H:%M:%S')}' order by tsi_mean_percentage desc"
    #     cursor.execute(sql)
    #     tsi_mean_percentages_of_day = cursor.fetchall()
    #     for index, item in enumerate(tsi_mean_percentages_of_day):
    #         sql = f"UPDATE {DATABASE}.ranks_calculations SET `tsi_mean_percentage_rank`={index+1} WHERE `id`={item['id']}"
    #         cursor.execute(sql)
    #     db_connection.commit()

    for rsl_date in rsl_days_dates[len(rsl_days_dates)-int(settings['reported_days']):]:
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


@app.route('/calculate-all-stock-rsi', methods=['GET'])
def calculate_all_stock_rsi():
    settings = get_stock_rsi_settings()
    db_connection = get_database_connection()
    cursor = db_connection.cursor(dictionary=True)
    sql = f"delete from `all_ranks_calculations`"
    cursor.execute(sql)
    db_connection.commit()
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
            all_price_data_of_rsl_days = all_price_data[(len(all_price_data) - int(settings['days_period_RSL'])):]
            # Step 1 Calculation
            for day_price_record in all_price_data_of_rsl_days:
                if(len(rsl_days_dates) != int(settings['days_period_RSL'])):
                    rsl_days_dates.append(day_price_record['date'])
                RSL_period_data = all_price_data[(all_price_data.index(day_price_record) - int(settings['days_period_RSL'])) : all_price_data.index(day_price_record) - 1]
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


    for wl in watchlists: # Iterating all watchlists
        sql = f"SELECT * FROM {DATABASE}.input WHERE `watchlist_id`={wl['id']}"
        cursor.execute(sql)
        wl_items = cursor.fetchall()
        for wli in wl_items:
            for rsl_date in rsl_days_dates[len(rsl_days_dates)-int(settings['reported_days']):]:
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

    for rsl_date in rsl_days_dates[len(rsl_days_dates)-int(settings['reported_days']):]:
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
    sql = f"select * from ranks_calculations rc where watchlist_id = {request.args.get('wl_id')} and tsi_mean_percentage is not null"
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
    sql = f"select * from all_ranks_calculations rc where tsi_mean_percentage is not null"
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


if __name__ == '__main__':
    app.run(host="localhost", port=8000, debug=True)
