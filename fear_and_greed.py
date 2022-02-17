from datetime import datetime as dt
import time
import mysql.connector
from mysql.connector import Error

from fng_index.CNNFearAndGreedIndex import CNNFearAndGreedIndex



SERVER = 'localhost'
DATABASE = 'stock_rsi'
USERNAME = 'zubair'
PASSWORD = 'lahore2020'



def get_database_connection():

    # Makes a connection with Database and return Connection Object
    connection = None
    try:
        # Creating Database connection object
        connection = mysql.connector.connect(
            host=SERVER,
            user=USERNAME,
            passwd=PASSWORD,
            database=DATABASE,
            auth_plugin='mysql_native_password'
        )
        return connection
    except Error as ex:
        print(f"Exception Occured: \n{ex}")

    return connection

if __name__ == '__main__':
    print('Pulling Fear & Greed Information ...')
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
    print('Fear & Greed Data Scrapped successfully.')
    time.sleep(5)