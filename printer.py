import socket
from requests import post

# IP-Adresse und Port des Druckers
HOST = "192.168.178.29"
PORT = 3000


MIDDLEMAN = "http://localhost:60000"
AUTH = (1, "loerrach")
blackbox_id = "1"


class Printer:

    def __init__(self, host, port):
        self.__host = host
        self.__port = port
        self.__socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self.__text = ''
        self.__order_id = 0

        self.__last_correct_command = 0
        self.__total_command_count = 0

    def connect(self):
        try:
            self.__socket.connect((self.__host, self.__port))
        except Exception as e:
            raise ConnectionError(f"Fehler beim Verbinden mit dem Drucker: {e}")

    def disconnect(self):
        sock_state = self.__socket.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR)
        if sock_state != 0:
            print("Socket wird noch verwendet.")
            return

        # Schließen des Sockets, wenn er nicht mehr verwendet wird
        self.__socket.close()
        print("Socket erfolgreich geschlossen.")

    def handle(self, feedback):
        printer_feedback = feedback.decode()
        if printer_feedback.startswith("ok N:"):
            self.__last_correct_command += 1
        # print(f"Empfangen: {printer_feedback}")

    def percent(self):
        return (self.__last_correct_command / self.__total_command_count) * 100

    def load_gcode(self, filestream: str, offset: int):
        commands = []

        gcode_commands = filestream.split('\n')
        for cmd in gcode_commands:
            if cmd.startswith(";"):
                continue

            commands.append(cmd.strip())

        self.__total_command_count = len(commands)
        return commands[offset:]

    def send_commands(self, commands, order_id):
        for cmd in commands:

            self.__socket.send(cmd.encode())
            feedback = self.__socket.recv(1024)
            self.handle(feedback)

            print(f"({self.__last_correct_command}/{self.__total_command_count})", cmd)

        post(MIDDLEMAN + f"/done/{order_id}", auth=AUTH)

    def start(self, text: str, order_id: int, offset=0):
        self.__text = text
        self.__order_id = order_id

        try:
            self.connect()
            gcode_commands = self.load_gcode(text, offset)
            self.send_commands(gcode_commands, order_id)

        finally:
            self.disconnect()

    def abort(self):
        self.disconnect()
        print("Druckvorgang abgebrochen.")
