from flask import Flask, request, make_response, jsonify
from requests import post
from time import sleep
from threading import Thread
from io import BytesIO
from json import loads, dumps

from Crypto.PublicKey import RSA
from Crypto.Cipher import AES, PKCS1_OAEP

import printer

app = Flask(__name__)
prnt = printer.Printer(printer.HOST, printer.PORT)

private_key = RSA.import_key(open("blackbox.pem", 'rb').read(), "password")

MIDDLEMAN = "http://localhost:60000"
AUTH = (1, "loerrach")
blackbox_id = "1"


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

    return make_response(jsonify({"percentage": prnt.percent()}), 200)


@app.route("/control", methods=["POST"])
def set_status():
    json = request.json
    return make_response("Success", 200)


@app.route("/print/<offset>", methods=["POST"])
def process_order(offset):

    json = request.json

    encrypted_file = BytesIO(bytes.fromhex(json["file"]))

    encrypted_session_key = encrypted_file.read(private_key.size_in_bytes())
    nonce = encrypted_file.read(16)
    tag = encrypted_file.read(16)
    encrypted_file = encrypted_file.read()

    cipher_rsa = PKCS1_OAEP.new(private_key)
    session_key = cipher_rsa.decrypt(encrypted_session_key)

    cipher = AES.new(session_key, AES.MODE_EAX, nonce)
    file = cipher.decrypt_and_verify(encrypted_file, tag).decode()

    set_current_order({"file": file, "order_id": json["order_id"]})
    t = Thread(target=prnt.start, kwargs={"text": file, "order_id": json["order_id"],
                                          "offset": int(offset)})
    t.start()

    return make_response("Started printing!", 200)


@app.route("/print_again", methods=["POST"])
def process_order_again():

    cur_order = get_current_order()
    t = Thread(target=prnt.start, kwargs={"text": cur_order["file"], "order_id": cur_order["order_id"]})
    t.start()

    return make_response("Started printing!", 200)


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=1234)
