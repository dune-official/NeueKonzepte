from flask import Flask, request, jsonify, make_response
from dataset import connect
from requests import get, post

from Crypto.PublicKey import RSA
from Crypto.Random import get_random_bytes
from Crypto.Cipher import AES, PKCS1_OAEP

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


def print_again(order_id, count_now) -> bool:
    order_info = connection.get_table("order").find_one(order_id=order_id)
    return count_now < order_info["count"]


def send_mail(manufacturer_id, content):

    print(f"Sending mail to {manufacturer_id}:")
    print(content)


@app.route("/")
def index():
    return "Welcome to the internet"


def login(auth, is_printer: bool = False):
    return auth and authenticate(auth.username, auth.password, is_printer)


@app.route("/order", methods=["POST"])
def order():
    if not login(request.authorization):
        return make_response("Could not verify!", 401, {"WWW-Authenticate": "Basic realm=\"Login Required\""})

    bb = connection.get_table("blackbox")

    json = request.json
    bb_single = bb.find_one(blackbox_id=json["blackbox_id"])

    if not bb_single:
        return make_response("Invalid blackbox ID", 404)

    if bb_single["printer_status"] == 0:
        # set the printer status as fast as possible to avoid a race condition
        bb.update(dict(blackbox_id=json["blackbox_id"], printer_status=1), ["blackbox_id"])

    order_table = connection.get_table("order")

    # encrypt the file
    file = bytes.fromhex(json["file"])
    pkey = RSA.import_key(open("blackbox_pub.pem").read())
    session_key = get_random_bytes(16)

    rsa_cipher = PKCS1_OAEP.new(pkey)
    enc_session_key = rsa_cipher.encrypt(session_key)

    cipher = AES.new(session_key, AES.MODE_EAX)
    encrypted_file, tag = cipher.encrypt_and_digest(file)

    encrypted_file = enc_session_key + cipher.nonce + tag + encrypted_file

    json["file"] = encrypted_file.hex()

    # the custom order does not matter, the database has a trigger that updates it to the row id anyway
    # it just has to be present
    order_id = order_table.insert(dict(description=json.get("description", ''), count=json["count"],
                                       file=json["file"], blackbox_id=json["blackbox_id"],
                                       manufacturer_id=request.authorization.username, status=0,
                                       custom_order=0))

    if bb_single["printer_status"] == 0:
        # we can start printing now

        response = post(bb_single["address"] + "/print", json=json | {"order_id": order_id})
        if response.status_code != 200:
            return make_response("Could not start printing process", 400)

        return make_response(jsonify(order_id=order_id), 200)

    return make_response(jsonify(order_id=order_id), 201)


@app.route("/queue/<blackbox_id>", methods=["GET"])
@app.route("/queue/<blackbox_id>/full", methods=["GET"])
def get_queue(blackbox_id):
    if not login(request.authorization, True):
        return make_response("Could not verify!", 401, {"WWW-Authenticate": "Basic realm=\"Login Required\""})

    rng = request.args.get("range")
    unresolved = connection.query(f"SELECT order_id FROM \"order\" "
                                  f"WHERE blackbox_id IS {blackbox_id} "
                                  f"{'AND status IS 0 ' if not request.path.endswith('/full') else ''} "
                                  f"ORDER BY custom_order "
                                  f"{'LIMIT ' + str(rng) if rng is not None else ''} ")

    lst = []
    for element in unresolved:
        lst.append(element["order_id"])

    return jsonify(queued=lst)


@app.route("/blackbox/location", methods=["GET"])
def location(location):
    return "1"


def get_next(blackbox_id):
    # todo: make dummy account
    return get(f"http://localhost:5000/queue/{blackbox_id}?range=1", auth=("1", "loerrach")).json()


def clear_queue(order_id, blackbox_id, blackbox_address):

    order_table = connection.get_table("order")

    order_table.update(dict(order_id=order_id, status=1), ["order_id"])
    next_element = get_next(blackbox_id)
    if not next_element["queued"]:
        connection.get_table("blackbox").update(dict(blackbox_id=blackbox_id, printer_status=0),
                                                ["blackbox_id"])
        return

    post(blackbox_address + "/print", json=order_table.find_one(order_id=next_element["queued"][0]))


@app.route("/status/<order_id>", methods=["GET"])
def get_status(order_id):
    if not login(request.authorization):
        return make_response("Could not verify!", 401, {"WWW-Authenticate": "Basic realm=\"Login Required\""})

    # todo: make this endpoint do something

    return {"orderID": order_id, "statusCode": 0, "progress": 60.123}


@app.route("/error/<order_id>", methods=["POST"])
def printer_error(order_id):
    if not login(request.authorization, True):
        return make_response("Could not verify!", 401, {"WWW-Authenticate": "Basic realm=\"Login Required\""})

    connection.get_table("order").update(dict(order_id=order_id, status=2), ["order_id"])
    order_ = connection.get_table("order").find_one(order_id=order_id)
    send_mail(order_["manufacturer_id"], request.json["log"])
    send_mail(order_["blackbox_id"], request.json["log"])

    return make_response("Error log sent", 200)


@app.route("/done/<order_id>", methods=["POST"])
def order_done(order_id):
    if not login(request.authorization, True):
        return make_response("Could not verify!", 401, {"WWW-Authenticate": "Basic realm=\"Login Required\""})

    order_done_table = connection.get_table("order_done")
    done_already = order_done_table.find_one(order_id=order_id)
    blackbox_address = connection.get_table("blackbox").find_one(blackbox_id=request.authorization.username)["address"]

    exists = connection.get_table("order").find_one(order_id=order_id)
    if exists is None:
        return make_response("Unable to find order", 404)

    if done_already is None:
        order_done_table.insert(dict(order_id=order_id, count=1))

        if print_again(order_id, 1):
            post(blackbox_address + "/print_again")
            return make_response("Created, print again", 200)
        else:
            # clear the printer status and free the queue
            clear_queue(order_id, exists["blackbox_id"], blackbox_address)
            return make_response("Created, forbidden to print again", 403)

    # failsafe
    if exists["status"] == 1 or done_already["count"] == exists["count"]:
        return make_response("Order done, forbidden to print again", 403)

    order_done_table.update(dict(order_id=order_id, count=done_already["count"] + 1), ["order_id"])

    if print_again(order_id, done_already["count"] + 1):
        post(blackbox_address + "/print_again")
        return make_response("Updated, print again", 200)
    else:
        # clear the printer status and free the queue
        clear_queue(order_id, exists["blackbox_id"], blackbox_address)
        return make_response("Updated, forbidden to print again", 403)


@app.route("/blackbox/<blackbox_id>", methods=["GET", "PUT"])
def control_blackbox(blackbox_id):
    if not login(request.authorization, True):
        return make_response("Could not verify!", 401, {"WWW-Authenticate": "Basic realm=\"Login Required\""})

    # todo: create blackbox api

    # -1: unavailable
    # 0: not busy
    # 1: busy (printing)
    # 2: busy (pause)
    # 3: error

    blackbox_table = connection.get_table("blackbox")
    blackbox_information = blackbox_table.find_one(blackbox_id=blackbox_id)

    if blackbox_information is None:
        return make_response("Unable to find blackbox", 404)

    if request.method == "PUT":
        json = request.json
        blackbox_table.update(json, ["blackbox_id"])
        return make_response("Success", 200)

    info = get(blackbox_information["address"] + "/info", auth=request.authorization)
    if not info.status_code == 200:
        return make_response(info.status_code)

    return info.json()


@app.route("/reorder", methods=["POST"])
def reorder():
    if not login(request.authorization, True):
        return make_response("Could not verify!", 401, {"WWW-Authenticate": "Basic realm=\"Login Required\""})

    swap = request.args.get("order1")
    with_ = request.args.get("order2")

    if swap is None or with_ is None:
        return make_response("order1 and order2 need to be present", 403)

    temp = connection.get_table("order").find_one(order_id=swap)
    temp2 = connection.get_table("order").find_one(order_id=with_)
    connection.get_table("order").update(dict(order_id=with_, custom_order=temp["custom_order"]), ["order_id"])
    connection.get_table("order").update(dict(order_id=swap, custom_order=temp2["custom_order"]), ["order_id"])

    return make_response("Successfully swapped orders", 200)


if __name__ == '__main__':
    app.run(host="0.0.0.0")
