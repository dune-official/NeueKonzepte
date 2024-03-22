from flask import Flask, request, make_response
from requests import post
from time import sleep
from threading import Thread

from json import loads, dumps

app = Flask(__name__)

MIDDLEMAN = "http://localhost:5000"
AUTH = (1, "loerrach")
blackbox_id = "1"

# todo: implement basic auth and check in any function


def get_current_order() -> dict:
    return loads(open("current_order.json", 'r').read())


def set_current_order(json: dict):
    open("current_order.json", 'w').write(dumps(json))


def print_file():

    current = get_current_order()

    file = current.get("file")
    if file is None:
        return

    # random conversion to stall time
    file = bytes.fromhex(file).hex()

    print(f"\n-- Printing order \"{current['description']}\" --")
    for letter in file:
        print(letter, end='')
        sleep(.5)

    print()

    input("Press enter to confirm printer tray is clear")
    print(f"-- Finished printing \"{current['description']}\" --")

    post(MIDDLEMAN + f"/done/{current['order_id']}", auth=AUTH)


@app.route("/info", methods=["GET"])
def info():

    # todo: decide what to return

    return


@app.route("/control", methods=["POST"])
def set_status():

    json = request.json

    # todo: handle that somehow, preferably with Samuel

    return make_response("Success", 200)


@app.route("/print", methods=["POST"])
async def process_order():

    # todo: actually print the file

    set_current_order(request.json)

    t = Thread(target=print_file)
    t.start()

    return make_response("Started printing!", 200)


@app.route("/print_again", methods=["POST"])
async def process_order_again():

    # todo: actually print the file

    t = Thread(target=print_file)
    t.start()

    return make_response("Started printing!", 200)


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=1234)
