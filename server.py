import socket
import threading
import queue
import pickle
import time
import random
from config import *
from main_server import mapSegment

outgoingQ = queue.Queue()


class ThreadedServer(threading.Thread):
    def __init__(self):
        super(ThreadedServer, self).__init__()
        self.plist = []
        self.pos_list = []
        self.host = '0.0.0.0'
        while True:
            try:
                self.port = random.randint(5000, 50000)

                self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.sock.bind((self.host, self.port))
                break
            except Exception:
                pass

        self.q = queue.Queue()
        # q to send to main server
        self.main_q = queue.Queue()

        # connect to main server
        self.main_address = ('10.100.102.27', 8080)
        self.listenToServer = listenToServer(self.main_address, self.port, self.main_q)
        self.listenToServer.start()

        send_server = sendToServer(self.main_q)
        send_server.start()
        send_client = sendToClient(self.q)
        send_client.start()

    def run(self):
        moves = []
        while True:
            data = self.sock.recvfrom(1024)
            address = data[1]
            pos = pickle.loads(data[0])
            if type(pos[0][0]) == int:
                print(pos[0])
                self.pos_list.append(pos[0])

                client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

                while True:
                    try:
                        port = random.randint(10000, 65535)
                        client.bind((self.host, port))
                        break
                    except Exception as error:
                        print(error)

                self.q.put([str(port), address, self.sock])

                p = listenToClient(client, address, self.plist, self.pos_list, self.listenToServer, self.q, moves)
                self.plist.append(p)
                p.start()
                moves = []
            else:
                moves += pos[0]


class listenToClient(threading.Thread):
    def __init__(self, client, address, plist, pos_list, server, q, moves):
        super(listenToClient, self).__init__()
        self.client = client
        self.address = address
        self.server = server

        self.plist = plist
        self.pos_list = pos_list
        self.pos = self.pos_list[-1]
        self.shot_dict = {}

        self.size = 1024

        self.q = q
        self.massage = queue.Queue()

        self.running = True

        self.calculate = threading.Thread(target=self.calculate)
        for move in moves:
            self.massage.put(move)
        self.calculate.start()

    def run(self):
        print('running ', self.address)
        # thread that calculate the positions
        while True:
            try:
                data = self.client.recvfrom(self.size)
                data = pickle.loads(data[0])
                massage = data[0]
                if massage == b'exit' or not self.running:
                    var = massage - 1
                for msg in massage:
                    self.massage.put(msg)
            except Exception as error:
                if str(error) == "unsupported operand type(s) for -: 'bytes' and 'int'":
                    print('client disconnected')
                elif str(error) == "[WinError 10038] An operation was attempted on something that is not a socket":
                    print('client moved to another server')
                else:
                    print('There was an error: ' + str(error))
                for i in range(len(self.plist)):
                    if self == self.plist[i]:
                        self.plist[i] = ''
                        self.pos_list[i] = ['', '']
                self.client.close()
                return

    def calculate(self):
        while self.running:
            self.change_location()
            self.calc_other_players()
        return

    def change_location(self):
        while not self.massage.empty():
            move = self.massage.get()
            if type(move) == str:
                movement = move.split(' ')

                for move in movement:
                    if move == 'l':
                        self.pos[0] -= PLAYER_SPEED
                    if move == 'r':
                        self.pos[0] += PLAYER_SPEED
                    if move == 'u':
                        self.pos[1] -= PLAYER_SPEED
                    if move == 'd':
                        self.pos[1] += PLAYER_SPEED
            else:
                if move[1] != -1 and move[2] != -1:
                    dx = abs(320 - move[1])
                    dy = abs(240 - move[2])
                    if 320 > move[1]:
                        x = self.pos[0] - dx
                    else:
                        x = self.pos[0] + dx
                    if 240 > move[2]:
                        y = self.pos[1] - dy
                    else:
                        y = self.pos[1] + dy
                    self.shot_dict[move[0]] = [x, y]
                else:
                    if self.shot_dict.get(move[0]):
                        self.shot_dict.pop(move[0])
        self.check_edge()
        self.check_out()

    def calc_other_players(self):
        personal_pos = ['positions']
        for pos in self.pos_list:
            if pos != ['', '']:
                if pos != self.pos:
                    dx = abs(self.pos[0] - pos[0])
                    dy = abs(self.pos[1] - pos[1])
                    if self.pos[0] > pos[0]:
                        x = 320 - dx
                    else:
                        x = 320 + dx
                    if self.pos[1] > pos[1]:
                        y = 240 - dy
                    else:
                        y = 240 + dy
                    if -32 < y < 480 and -32 < x < 640:
                        personal_pos.append(['p', x, y])
        for player in self.plist:
            if player != self and player != '':
                for shot in player.shot_dict:
                    pos = player.shot_dict[shot]
                    dx = abs(self.pos[0] - pos[0])
                    dy = abs(self.pos[1] - pos[1])
                    if self.pos[0] > pos[0]:
                        x = 320 - dx
                    else:
                        x = 320 + dx
                    if self.pos[1] > pos[1]:
                        y = 240 - dy
                    else:
                        y = 240 + dy
                    if -32 < y < 480 and -32 < x < 640:
                        personal_pos.append(['s', x, y])
        self.q.put([personal_pos, self.address, self.client])
        time.sleep(0.01)

    def check_out(self):
        if self.server.map_seg.is_out_of_bounds(self.pos):
            self.q.put([['move', self.pos], self.address, self.client])
            time.sleep(0.5)
            self.running = False
            for i in range(len(self.plist)):
                if self == self.plist[i]:
                    self.plist[i] = ''
                    self.pos_list[i] = ['', '']
            self.client.close()

    def check_edge(self):
        edge_dict = {}
        for i in range(len(self.plist)):
            if self.plist[i] == self:
                break
        if self.server.map_seg.is_edge(self.pos):
            edge_dict['p'] = self.pos
        for pos in self.shot_dict:
            if self.server.map_seg.is_edge(self.shot_dict[pos]):
                edge_dict[pos] = self.shot_dict[pos]
        if edge_dict != {}:
            self.server.main_q.put([self.server.main_server, edge_dict])


class sendToClient(threading.Thread):
    def __init__(self, q):
        super(sendToClient, self).__init__()
        self.size = 1024
        self.q = q

    def run(self):
        while True:
            try:
                if not self.q.empty():
                    message = self.q.get()
                    client = message[2]
                    client.sendto(pickle.dumps(message[0]), message[1])
            except Exception:
                pass


class listenToServer(threading.Thread):
    def __init__(self, address, port, main_q):
        super(listenToServer, self).__init__()
        self.massage = None
        self.main_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.address = address
        self.main_server.connect(address)
        self.size = 1024
        self.main_q = main_q
        message = ['server', port]
        self.main_q.put([self.main_server, message])

    def run(self):
        # print('running ', self.address)
        # thread that calculate the positions
        while True:
            try:
                data = self.main_server.recv(self.size)
                massage = pickle.loads(data)
                if massage[0] == 'map':
                    self.map_seg = massage[1]
            except Exception as error:
                self.main_server.close()
                return


class sendToServer(threading.Thread):
    def __init__(self, q):
        super(sendToServer, self).__init__()
        self.size = 1024
        self.q = q

    def run(self):
        while True:
            if not self.q.empty():
                message = self.q.get()
                message[0].send(pickle.dumps(message[1]))
            time.sleep(0.1)


if __name__ == "__main__":
    Ts = ThreadedServer()
    Ts.start()
    Ts.join()
