from flask import Flask, request, jsonify, make_response
from requests import get, post

app = Flask(__name__)

MIDDLEMAN = "http://localhost:5000"
AUTH = (1, "loerrach")
blackbox_id = "1"

# todo: implement basic auth and check in any function


async def print_file(json: dict):
    # todo: handle that somehow, preferably with Samuel

    file = json.get("file")
    if file is None:
        return

    file = bytes.fromhex(file)

    print("\n-- Printing order --")
    print(file.hex().upper())
    print()


@app.route("/info", methods=["GET"])
def info():

    # todo: decide what to return

    return


@app.route("/set", methods=["POST"])
def set_status():

    json = request.json

    # todo: handle that somehow, preferably with Samuel

    return make_response("Success", 200)


@app.route("/print", methods=["GET", "POST"])
async def process_order():

    if request.method == "GET":
        # -1: unavailable
        # 0: not busy
        # 1: busy (printing)
        # 2: busy (pause)
        # 3: error

        # todo: actually do this
        return jsonify(status=0)

    # todo: actually print the file
    await print_file(request.json)

    return make_response("Started printing!", 200)


@app.route("/done/<order_id>")
async def current_file_done(order_id):

    response = post(MIDDLEMAN + f"/done/{order_id}", auth=AUTH)

    if response.status_code == 401:
        # todo: handle error
        return make_response("Failed to authenticate", 401)

    if response.status_code == 200:

        # todo: print order again
        return make_response("Continuing printing", 200)

    if response.status_code == 404:

        # todo: handle error
        return make_response("Could not find order", 404)

    if response.status_code == 403:

        # get next printing order of the queue
        response = get(MIDDLEMAN + f"/printnext/{blackbox_id}", auth=AUTH)
        if response.status_code == 200:

            await print_file(request.json)

        return make_response("Stopping to print, delete file", 403)


if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=1234)
