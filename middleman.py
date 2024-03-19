from flask import Flask, request, jsonify, make_response
# flask: pip install flask[asyncio]
from dataset import connect
from requests import get, post

connection = connect("sqlite:///database")
app = Flask(__name__)


def authenticate(username, password, is_printing: bool = False):
    if is_printing:
        result = connection.get_table("printer_company_login").find_one(printer_company_id=username,
                                                                        printer_company_password=password)
    else:
        result = connection.get_table("manufacturer_login").find_one(manufacturer_id=username,
                                                                     manufacturer_password=password)

    return result is not None


def print_again(order_id, count_now):
    order_info = connection.get_table("order").find_one(order_id=order_id)
    return count_now < order_info["count"]


@app.route("/")
def index():
    return "Welcome to the internet"


def login(auth, is_printer: bool = False):
    return auth and authenticate(auth.username, auth.password, is_printer)


@app.route("/order", methods=["POST"])
def order():
    if not login(request.authorization):
        return make_response("Could not verify!", 401, {"WWW-Authenticate": "Basic realm=\"Login Required\""})

    json = request.json
    order_table = connection.get_table("order")

    order_id = order_table.insert(dict(description=json.get("description", ''), count=json["count"], file=json["file"],
                                       blackbox_id=json["blackbox_id"], manufacturer_id=request.authorization.username,
                                       done=0))

    bb = connection.get_table("blackbox")
    bb_single = bb.find_one(blackbox_id=json["blackbox_id"])

    if not bb_single:
        return make_response("Invalid blackbox ID", 404)

    if bb_single["printer_status"] == 0:
        # we can start printing now

        response = post(bb_single["location"] + "/print", json={"file": json["file"], "order_id": order_id})
        if response.status_code != 200:
            return make_response("Could not start printing process", 400)

        bb.update(dict(blackbox_id=json["blackbox_id"], printer_status=1), ["blackbox_id"])
        return make_response("Started printing", 200)

    return make_response("Added to the queue", 201)


@app.route("/queue/<blackbox_id>", methods=["GET"])
def get_queue(blackbox_id):
    if not login(request.authorization, True):
        return make_response("Could not verify!", 401, {"WWW-Authenticate": "Basic realm=\"Login Required\""})

    rng = request.args.get("range")

    order_table = connection.get_table("order")
    unresolved = order_table.find(blackbox_id=blackbox_id, done=0)

    lst = []
    if rng is not None:
        limit = rng
    else:
        # negative values don't reach 0 anymore
        limit = -1

    for element in unresolved:
        lst.append(element["order_id"])

        limit -= 1
        if limit == 0:
            break

    return jsonify(queued=lst)


@app.route("/blackbox/location", methods=["GET"])
def location():
    return "1"


@app.route("/printnext/<blackbox_id>", methods=["GET"])
def print_next(blackbox_id):
    if not login(request.authorization, True):
        return make_response("Could not verify!", 401, {"WWW-Authenticate": "Basic realm=\"Login Required\""})

    order_table = connection.get_table("order")
    unresolved = order_table.find(blackbox_id=blackbox_id, done=0)
    nxt = next(unresolved)

    bb = connection.get_table("blackbox")
    bb_single = bb.find_one(blackbox_id=blackbox_id)

    response = post(bb_single["location"] + "/print", json={"file": nxt["file"]})
    if response.status_code != 200:
        return make_response("Could not start printing process", 400)

    bb.update(dict(blackbox_id=blackbox_id, printer_status=1), ["blackbox_id"])
    return make_response("Started printing", 200)


@app.route("/status/<order_id>", methods=["GET"])
def get_status(order_id):
    if not login(request.authorization):
        return make_response("Could not verify!", 401, {"WWW-Authenticate": "Basic realm=\"Login Required\""})

    return order_id


@app.route("/error/<order_id>", methods=["POST"])
def printer_error(order_id):
    if not login(request.authorization, True):
        return make_response("Could not verify!", 401, {"WWW-Authenticate": "Basic realm=\"Login Required\""})

    return order_id


@app.route("/done/<order_id>", methods=["POST"])
def order_done(order_id):
    if not login(request.authorization, True):
        return make_response("Could not verify!", 401, {"WWW-Authenticate": "Basic realm=\"Login Required\""})

    order_done_table = connection.get_table("order_done")
    done_already = order_done_table.find_one(order_id=order_id)

    exists = connection.get_table("order").find_one(order_id=order_id)
    if exists is None:
        return make_response("Unable to find order", 404)

    if done_already is None:
        order_done_table.insert(dict(order_id=order_id, count=1))

        if print_again(order_id, 1):
            return make_response("Created, print again", 200)
        else:
            # clear the printer status and free the queue
            connection.get_table("order").update(dict(order_id=order_id, done=1), ["order_id"])
            connection.get_table("blackbox").update(dict(blackbox_id=exists["blackbox_id"], printer_status=0),
                                                    ["blackbox_id"])
            return make_response("Created, forbidden to print again", 403)

    if exists["done"] == 1 or done_already["count"] == exists["count"]:
        return make_response("Order done, forbidden to print again", 403)

    order_done_table.update(dict(order_id=order_id, count=done_already["count"] + 1), ["order_id"])

    if print_again(order_id, done_already["count"] + 1):
        return make_response("Updated, print again", 200)
    else:
        # clear the printer status and free the queue
        connection.get_table("order").update(dict(order_id=order_id, done=1), ["order_id"])
        connection.get_table("blackbox").update(dict(blackbox_id=exists["blackbox_id"], printer_status=0),
                                                ["blackbox_id"])
        return make_response("Updated, forbidden to print again", 403)


@app.route("/printer/<blackbox_id>", methods=["GET"])
# todo: mark this as obsolete
def get_printer_status(blackbox_id):
    if not login(request.authorization, True):
        return make_response("Could not verify!", 401, {"WWW-Authenticate": "Basic realm=\"Login Required\""})

    # todo: create blackbox api

    blackbox_table = connection.get_table("blackbox")
    blackbox_information = blackbox_table.find_one(blackbox_id=blackbox_id)

    if blackbox_information is None:
        return make_response("Unable to find blackbox", 404)

    printer_status = get(blackbox_information["location"] + "/print", auth=request.authorization)
    blackbox_table.update(dict(blackbox_id=blackbox_id, printer_status=printer_status), ["blackbox_id"])

    # -1: unavailable
    # 0: not busy
    # 1: busy (printing)
    # 2: busy (pause)
    # 3: error

    return jsonify(printer_status=blackbox_information["printer_status"])


@app.route("/blackbox/<blackbox_id>", methods=["GET", "PUT"])
def control_blackbox(blackbox_id):
    if not login(request.authorization, True):
        return make_response("Could not verify!", 401, {"WWW-Authenticate": "Basic realm=\"Login Required\""})

    # todo: create blackbox api

    blackbox_table = connection.get_table("blackbox")
    blackbox_information = blackbox_table.find_one(blackbox_id=blackbox_id)

    if blackbox_information is None:
        return make_response("Unable to find blackbox", 404)

    if request.method == "PUT":
        json = request.json
        blackbox_table.update(json, ["blackbox_id"])
        return make_response("Success", 200)

    info = get(blackbox_information["location"] + "/info", auth=request.authorization)
    if not info.status_code == 200:
        return make_response(info.status_code)

    return info.json()


if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0")
