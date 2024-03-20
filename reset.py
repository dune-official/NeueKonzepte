from dataset import connect

connection = connect("sqlite:///database")


# this script cleans the tables to a "before" state (but keeping the manufacturers and blackboxes/printing companies)


def purge_table_sqlite(table_name):
    connection.query(f"DELETE FROM \"{table_name}\";")
    connection.query(f"DELETE FROM SQLITE_SEQUENCE WHERE name='{table_name}';")


def set_value_column(table_name, column_name, value):
    connection.query(f"UPDATE {table_name}\n SET {column_name} = '{value}';")


purge_table_sqlite("order")
purge_table_sqlite("order_done")

set_value_column("blackbox", "printer_status", 0)
