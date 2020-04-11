from socketserver import StreamRequestHandler, ThreadingTCPServer
import socket
import ssl
from util.server_settings import *
from common.sftp_msg import *
from util.server_util import *
from util.mysql_helper import MySQLHelper
import json
from transitions.extensions import HierarchicalGraphMachine


class SFTP_Server(ThreadingTCPServer):
    """
    支持SSL的 socketserver,
    """
    def server_bind(self):
        ThreadingTCPServer.server_bind(self)
        # wrap the socket early
        self.socket = ssl.wrap_socket(
            self.socket, server_side=True, certfile=CERT_PATH,
            keyfile="server.key",
            do_handshake_on_connect=False)

    def get_request(self):
        socket, addr = ThreadingTCPServer.get_request(self)
        print(f"与 {addr} 建立TCP连接")
        # postpone the handshake
        socket.do_handshake()
        return socket, addr


class MySSLHandler(StreamRequestHandler):
    # def __init__(self, request, client_address, server, *args, **kwargs):
    #     StreamRequestHandler.__init__(self, request, client_address, server)
    #     # 继承状态机 进行 管理
    #     HierarchicalMachine.__init__(self, states=STATES, transitions=TRANSITIONS)
    #     print("1111")
    #     self.get_graph().draw('Server.pdf', prog='dot')

    def delete_token(self):
        if self.token:
            remove_old_token(self.token)
            print(f"token:{self.token} has removed")

    def handle(self):
        print(f"与 {self.client_address} 建立TLS连接")
        self.data = None
        self.token = None
        # 文件数据传送 监听套接字
        self.data_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.data_sock.bind((SERVER_HOST, SERVER_DATA_PORT))
        # self.data_sock.listen(1)
        # self.data_sock.accept()
        # 文件数据传送 已连接套接字
        self.data_client_sock = None
        self.cur_file_info = None

        self.machine = HierarchicalGraphMachine(states=STATES, transitions=TRANSITIONS, **extra_args)
        self.machine.get_graph().draw('Server.pdf', prog='dot')
        while True:
            try:
                self.data = self.request.recv(1024).strip()             # 接收协议消息
                print("{} wrote:".format(self.client_address))
                print(self.data)
                ptype, ack, length, msg = sftp_msg.unpack(self.data)    # 拆包
                ret_pkg = deal_pkg(case=(ptype, ack), data=msg,         # “重载”函数处理
                                   handler_obj=self)                    # 保存一些关键数据, 如token
                # print(self.token)
                if ret_pkg:
                    self.request.sendall(ret_pkg)                       # 发送对应的数据包
            except ssl.SSLError:
                self.delete_token()
                print(self.client_address, '的SSL连接意外断开了！')
                self.request.close()
                self.data_sock.close()
                break
            except ConnectionResetError:
                self.delete_token()
                print(self.client_address, '的连接意外断开了！')
                self.request.close()
                self.data_sock.close()
                break
            # 判断客户端是否断开
            if not self.data:
                self.delete_token()
                print(self.client_address, '的连接断开了！')
                self.request.close()
                self.data_sock.close()
                break


if __name__ == "__main__":
    server = SFTP_Server(SERVER_URI, MySSLHandler)
    server.serve_forever()
