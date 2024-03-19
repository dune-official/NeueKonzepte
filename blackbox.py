from flask import Flask, request, jsonify, make_response
from requests import get

app = Flask(__name__)


# todo: implement basic auth and check in any function


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
def process_order():

    if request.method == "GET":
        # -1: unavailable
        # 0: not busy
        # 1: busy (printing)
        # 2: busy (pause)
        # 3: error

        # todo: actually do this
        return jsonify(status=0)

    json = request.json
    file = json["file"]

    file = bytes.fromhex(file)

    # todo: print the file

    return make_response("Started printing!", 200)
