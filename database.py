from constants import DATABASE, PASSWORD, SERVER, USERNAME
import mysql.connector
from mysql.connector import Error


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