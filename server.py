from socketserver import StreamRequestHandler, ThreadingTCPServer
import ssl
from util.server_settings import *
from common.sftp_msg import *
from util.server_util import deal_pkg, remove_old_token
from util.mysql_helper import MySQLHelper
import json


class ConnError(ConnectionResetError, ssl.SSLError):
    pass

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
        # postpone the handshake
        socket.do_handshake()
        return socket, addr


class MySSLHandler(StreamRequestHandler):
    def delete_token(self):
        if self.token:
            remove_old_token(self.token)
            print(f"token:{self.token} has removed")

    def handle(self):
        print(f"与 {self.client_address} 建立TLS连接")
        self.data = None
        self.token = None
        while True:
            try:
                self.data = self.request.recv(1024).strip()             # 接收协议消息
                print("{} wrote:".format(self.client_address))
                print(self.data)
                ptype, ack, length, msg = sftp_msg.unpack(self.data)    # 拆包
                ret_pkg = deal_pkg(case=(ptype, ack), data=msg,         # “重载”函数处理
                                   handler_obj=self)                    # 保存一些关键数据, 如token
                # print(self.token)
                self.request.sendall(ret_pkg)                           # 发送对应的数据包
            except ssl.SSLError:
                self.delete_token()
                print(self.client_address, '的SSL连接意外断开了！')
                break
            except ConnectionResetError:
                self.delete_token()
                print(self.client_address, '的连接意外断开了！')
                break
            # 判断客户端是否断开
            if not self.data:
                self.delete_token()
                print(self.client_address, '的连接断开了！')
                break


if __name__ == "__main__":
    server = SFTP_Server(SERVER_URI, MySSLHandler)
    server.serve_forever()
