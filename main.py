from typing import MutableSet
from database import get_database_connection
import flask
from flask import render_template, redirect, url_for
import io, os
from datetime import datetime as dt, timedelta
from flask import request
from helper_functions import parse_csv
from constants import DATABASE

import yahoo_fin.stock_info as si


app = flask.Flask(__name__, static_url_path='',
            static_folder='static',
            template_folder='template')

app.config["DEBUG"] = True


@app.route("/")
def csv_index():
    allow_pull = False
    db_connection = get_database_connection()
    cursor = db_connection.cursor(dictionary=True)
    sql = f"SELECT max(pull_date) as max_pull_date FROM {DATABASE}.pull_data_history"
    cursor.execute(sql)
    last_pulled_date = cursor.fetchall()[0]['max_pull_date']
    allow_pull = dt.strptime(last_pulled_date.strftime('%m/%d/%y %H:%M:%S'), '%m/%d/%y %H:%M:%S') < dt.now()
    db_connection.close()

    return render_template(
        "csv.html",
        last_pulled_date=last_pulled_date,
        allow_pull=allow_pull
    )


# Get the uploaded file
@app.route("/", methods=['POST'])
def upload_files():
    db_connection = get_database_connection()
    cursor = db_connection.cursor()
    # get the uploaded file
    uploaded_file = request.files['file']
    if uploaded_file.filename != '':
        file_path = os.path.join('/', uploaded_file.filename)
        # set the file path
        uploaded_file.save(file_path)
        csv_data = parse_csv(file_path)

    wl_name = uploaded_file.filename.split('_')[0]
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
               int(uploaded_file.filename.split('.')[0].split('_')[1]),
            )
        cursor.execute(sql, val)
    db_connection.commit()
    db_connection.close()

    return render_template('csv.html', csv_records=csv_data)


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
            db_connection.close()
            return render_template("watchlistIndex.html", watchlist_records=items)
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
        closing_price = cursor.fetchall()[0]
        items[index]['close_price'] = closing_price['close_price']
        items[index]['close_date'] = closing_price['date']

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
            closing_price = cursor.fetchall()[0]
            watchlist_item_to_edit['price'] = closing_price['close_price']
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
        sql = f"UPDATE {DATABASE}.input SET `company`='{ request.form.get('company')}', `symbol`='{ request.form.get('symbol')}', `price`={request.form.get('price')}, `watchlist_id`={request.form.get('watchlist_id')}, `datasource_id`={request.form.get('datasource_id')} WHERE `id`={request.form.get('id')}"
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
    db_connection = get_database_connection()
    cursor = db_connection.cursor(dictionary=True)
    # sql = f"SELECT * FROM {DATABASE}.watchlist"
    # cursor.execute(sql)
    # watchlists = cursor.fetchall()
    # for wl in watchlists:
    #     sql = f"SELECT * FROM {DATABASE}.input WHERE `watchlist_id`={wl['id']}"
    #     cursor.execute(sql)
    #     inputs = cursor.fetchall()
    #     for i in inputs:
    #         if(int(i['datasource_id']) == 1):
    #             sql = f"select max(date) as latest_price_date from price_data pd where symbol = '{i['symbol']}'"
    #             cursor.execute(sql)
    #             latest_price_data = cursor.fetchall()

    #             if(not bool(latest_price_data[0]['latest_price_date'])):
    #                 end_date = dt.now() - timedelta(days=1)
    #                 start_date = end_date - timedelta(days=199)
    #             else:
    #                 end_date = dt.now() - timedelta(days=1)
    #                 start_date = dt.strptime(latest_price_data[0]['latest_price_date'].strftime('%m/%d/%y %H:%M:%S'), '%m/%d/%y %H:%M:%S') + timedelta(days=1)

    #             df = si.get_data(
    #                 i['symbol'],
    #                 start_date = "{:02d}/{:02d}/{}".format(start_date.day, start_date.month, start_date.year),
    #                 end_date = "{:02d}/{:02d}/{}".format(end_date.day, end_date.month, end_date.year)
    #             )
    #             dates = df.index
    #             data = df.to_dict('records')
    #             for index, value in enumerate(data):
    #                 sql = f"INSERT INTO {DATABASE}.price_data (`symbol`, `close_price`, `date`, `datasource_id`)"
    #                 sql = sql+" values(%s, %s, %s, %s)"
    #                 val = (
    #                     i['symbol'],
    #                     value['close'],
    #                     str(dates[index]),
    #                     1
    #                 )
    #                 cursor.execute(sql, val)
    #             db_connection.commit()
    sql = f"INSERT INTO {DATABASE}.pull_data_history (`pull_date`)"
    sql = sql+" values(%s)"
    val = (dt.now(),)
    cursor.execute(sql, val)
    db_connection.commit()
    db_connection.close()
    breakpoint()
    return 'Data pull completed successfully'



if __name__ == '__main__':
    app.run(host="localhost", port=8000, debug=True)