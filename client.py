#!C:\Anaconda\python.exe
# -*- coding: utf-8 -*-
import socket
import ssl
# from transitions.extensions.factory import HierarchicalGraphMachine as Machine
from transitions.extensions import HierarchicalMachine as Machine
# from transitions.extensions.nesting import NestedState
from transitions import EventData
from common.settings import *
from client_utils import *
from common.sftp_msg import *
import getpass
import json
import os
from functools import partial
from typing import Union
# Machine.hierarchical_machine_attributes['ranksep'] = '0.3'  # shorter edges
# Machine.hierarchical_machine_attributes['fontname'] = "Inconsolata, Consolas"  # "Microsoft YaHei"


class STFP_Client(Machine):
    def __init__(self, server_uri: tuple = None, ssl_mode=False, cert_path=CERT_PATH):
        """
        客户端初始化
        :param server_uri: 服务器地址
        :param ssl_mode: 是否使用SSL
        :param cert_path: 服务器证书路径
        """
        # 状态机初始化
        Machine.__init__(self, states=STATES, transitions=TRANSITIONS, initial="INIT", send_event=True, **extra_args)
        self.__machine_init()

        # socket初始化
        self.raw_sock = socket.create_connection(server_uri)
        self.work_sock = None
        if ssl_mode:
            print('使用SSL模式加密传输')
            self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            self.context.load_verify_locations(cert_path)
            self.work_sock = self.context.wrap_socket(self.raw_sock, server_hostname=server_uri[0])
        else:
            print('不使用SSL')
            self.work_sock = self.raw_sock
        # 其他参数
        self.file_sock = None     # 传输文件专用 socket
        # 下载文件专用监听socket
        # self.down_listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # self.down_listen_sock.bind((SERVER_HOST, SERVER_DATA_PORT))
        # self.down_conn_sock = None  # 下载文件连接socket
        self.token = None       # 用户临时口令

    def __machine_init(self):
        """
        状态机初始化
        主要工作：
        1. 添加 transitions(可选，初始化时已完成)
        2. 设置输出图形参数
        3. 输出模型 (需要关闭 parallel 或 取消 自定义分隔符)
        """
        self.add_transitions([
            {   # 上传文件，自动覆盖重名文件
                'source': 'Running↦UP_MODE', 'dest': 'Running↦UP_MODE↦OverRide',
                'trigger': "Upload file(OverRide)",
                'after': partial(self.reqUploadFile, mode=1)
            },
            {   # 上传文件，不覆盖重名文件
                'source': 'Running↦UP_MODE', 'dest': 'Running↦UP_MODE↦Normal',
                'trigger': "Upload file(Normal)",
                'after': partial(self.reqUploadFile, mode=0)
            },
            {   # 上传文件状态 失败回退
                'source': ['Running↦UP_MODE↦OverRide', 'Running↦UP_MODE↦Normal'],
                'dest': 'Running↦UP_MODE',
                'trigger': "Ret_UP_MODE"
            },
            {   # 进入上传过程
                'source': ['Running↦UP_MODE↦OverRide', 'Running↦UP_MODE↦Normal'],
                'dest': 'Running↦UP_MODE↦UPLOADING',
                'trigger': "Upload",
                'prepare': "preUpload"
            },
            {   # 上传完毕回退
                'source': 'Running↦UP_MODE↦UPLOADING',
                'dest': 'Running↦UP_MODE',
                'trigger': "FinishUpload",
            },
            {  # 下载文件请求
                'source': 'Running↦DOWN_MODE', 'dest': 'Running↦DOWN_MODE↦reqDown',
                'trigger': "Download file",
                'before': 'reqDownloadFile'
            },
            {  # 下载文件请求 失败回退
                'source': 'Running↦DOWN_MODE↦reqDown',
                'dest': 'Running↦DOWN_MODE',
                'trigger': "Ret_DOWN_MODE"
            },
            {  # 进入下载过程
                'source': 'Running↦DOWN_MODE↦reqDown',
                'dest': 'Running↦DOWN_MODE↦DOWNLOADing',
                'trigger': "Download",
                'prepare': "preDownload"
            },
            {   # 下载完毕回退
                'source': 'Running↦DOWN_MODE↦DOWNLOADing', 'dest': 'Running↦DOWN_MODE',
                'trigger': "FinishDownload",
            }

        ])
        # 图像设置
        # self.style_attributes['edge']["default"]["fontname"] = "Microsoft YaHei"
        # self.get_graph().draw('SFTP_Machine.pdf', prog='dot')   # 输出当前状态机模型
        pass

    # 控制台界面
    def work(self):
        """
        以状态机为核心，进入循环过程
        1. 显示当前状态，2. 列出可以选择的 状态转换(功能)
        选择对应的 状态转换(功能) 编号，即可 "尝试" 进行状态转换
        转换过程 设定 回调函数，完成相应的逻辑功能
        """
        print('='*23, '= Welcome SFTP System =', sep='\n')    # 打印欢迎语
        while True:
            print("\033[31m=\033[0m"*23)    # 红色分割线 —— 新一轮交互/选择
            print(f"\033[0;32mCurrent State\033[0m: \033[1;32m{self.state}\033[0m")  # 1. 显示当前状态
            options = []  # 获取当前可以进行的操作
            extra = []
            if isinstance(self.state, list):  # 并行状态的情况
                # 需求：parent和子状态 的 triggers 区分开, 并且编号要合理
                # 解决：设置附加输出
                parent_state = self.state[0].split(NestedState.separator)[0]
                parent_triggers = self.get_triggers(parent_state)
                options += parent_triggers
                extra += [f' --- [{parent_state}]'] * len(parent_triggers)
                for sub_state in self.state:
                    sub_state_triggers = list_sub(self.get_triggers(sub_state), parent_triggers)
                    options += sub_state_triggers
                    extra += [f' --- [{sub_state}]'] * len(sub_state_triggers)
            else:
                options = self.get_triggers(self.state)
            # 2. 列出可以选择的 状态转换(功能)
            print_msg('\033[0;33mChoose your select\033[0m', options, extra)
            try:
                usr_input = int(input('\nPlease input the Client Command:\n'))  # 获取用户选择
                print(f'you choose {usr_input}:{options[usr_input]}\n')
                print("\033[35m=\033[0m" * 23)  # 紫色分割线 —— 接下来是跟状态转换相关的IO
                self.trigger(options[usr_input])    # 触发 transition，尝试状态转换
                # getattr(self, options[usr_input])()
            except IndexError:
                print('指令编号范围错误')
                continue
            except ValueError:
                print('请输入指令编号')
                continue
            except Exception as e:
                print("其他错误")
                print(e)

    # 网络IO函数
    def __sendmsg(self, type_, ack, msg: Union[dict, str], recv=False):
        """
        协议数据包 发送
        :param type: 数据包类型
        :param ack:  ACK
        :param msg:  消息
        :param recv: 是否 接收消息
        :return: 发送的字节数
        """
        msg = json.dumps(msg) if msg else msg
        pkg = sftp_msg(type_, ack, msg).pack()
        try:
            nSent = self.work_sock.send(pkg)
            print(f"发送字节数:{nSent}")
            if recv:
                return self.__recvmsg(type_)
            else:
                return nSent

        except ConnectionResetError as e:
            print('服务器掉线')
            return None

    def __recvmsg(self, type_):
        """
        接收 协议数据包
        :param type_: 数据包类型
        :return: (ack, msg) or None
        """
        ret_pkg = self.work_sock.recv(BUFFER_SIZE)  # 接收返回的数据包
        # print(ret_pkg)
        if ret_pkg is None:
            print("服务器返回None")
            return None
        ptype, ack, length, msg = sftp_msg.unpack(ret_pkg)  # 拆包
        if ptype == pkg_type.SERVER_ERROR:
            print("服务器错误: ", msg)
            return None
        assert ptype == type_
        print("server: ", msg)
        return ack, msg

    # 各种回调实现
    def reqSignUp(self, event):
        """
        注册逻辑实现
        状态转换：Init -> SignUpSuccess (if return True)
        """
        # 获取用户输入
        usr_name = input('>>>username:')
        passwd = getpass.getpass('>>>password:')
        # 组装SignUp数据包
        ret = self.__sendmsg(pkg_type.SignUp, 0, {"name": usr_name, "pwd": passwd}, recv=True)
        if ret is None:
            return False
        else:
            ack, msg = ret
            return True if ack is 1 else False

    def reqSignIn(self, event):
        """
        登录逻辑实现
        状态转换：Init -> Running (if return True)
        """
        usr_name = input('>>>username:')
        # passwd = getpass.getpass('>>>password:')
        passwd = input('>>>password:')
        ret = self.__sendmsg(pkg_type.SignIn, 0, {"name": usr_name, "pwd": passwd}, recv=True)
        if ret is None:
            return False
        ack, msg = ret
        if ack == 1:    # 登录成功
            msg = json.loads(msg)
            self.token = msg['token']
            return True
        else:
            return False

    def ReConnect(self, event):
        """
        重新连接服务器
        状态转换：Init (internal)
        """
        count = 0
        if self.work_sock._closed is False:
            self.work_sock.close()

        while self.work_sock._closed and count < 10:
            print(f"尝试重新连接{count}")
            count += 1
            self.work_sock = self.context.wrap_socket(socket.create_connection(SERVER_URI),
                                                      server_hostname=SERVER_URI[0])

    def on_enter_Running(self, event):
        """
        进入 Running(登录成功) 后回调
        """
        assert self.token is not None
        # print("token:", self.token)

    def on_exit_Running(self, event):
        """
        退出 Running(登录成功) 后回调
        """
        self.token = None

    def on_enter_EXIT(self, event):
        """
        进入 EXIT 回调
        退出程序
        """
        self.work_sock.close()
        exit()

    def reqSignOut(self, event):
        """
        请求 退出登录
        状态转换：Running -> INIT
        """
        self.__sendmsg(pkg_type.SignOut, 0, {"token": self.token})

    def reqRemoteDir(self, event):
        """
        显示远程目录
        内部状态转换：Running↦LS_MODE
        """
        ack, msg = self.__sendmsg(pkg_type.SHOW_LIST, 0, {"token": self.token}, recv=True)
        msg = json.loads(msg)
        if ack == 1:
            print("\033[35m=\033[0m" * 23)  # 紫色分割线
            print("\033[32mRemote File List:\033[0m")
            for file_name in msg["result"]:
                print(file_name)
            print("\033[35m=\033[0m" * 23)  # 紫色分割线
            while input("Press 'q' to return: ") is not 'q':
                pass
        else:
            print("Error: ", msg)

        pass

    def reqLocalDir(self, event):
        """
        显示本地目录
        内部状态转换：Running↦LS_MODE
        """
        file_list = get_local_dir()
        if file_list:
            [print(i) for i in file_list]
        else:
            print("No files in local dir")

    def reqUploadFile(self, event, mode=0):
        """
        上传文件
        Running子状态转换：UP_MODE --> UP_MODE↦Normal/OverRide
        after回调
        """
        print("current path:")
        print(os.path.abspath(os.curdir), end='\n\n')
        print("Input your file path: 'q' to exit ")
        # 输入了正确的文件路径才会退出while循环 或者输入q放弃
        while True:
            file_path = input('>>>file_path: ')
            if os.path.exists(file_path):
                break
            elif file_path is "q":  # 放弃上传
                self.trigger("Ret_UP_MODE")
                return False
        assert os.path.exists(file_path)
        # 发送 文件上传请求 数据包
        ret = self.__sendmsg(pkg_type.FILE_UPLD, mode, {
            "filename": os.path.basename(file_path),
            "filesize": os.path.getsize(file_path),
            "token": self.token
        })
        ack, msg = ret if ret else None, None
        if ack == 2:
            # 如果服务器端合适，手动触发状态转换
            # UP_MODE --> UP_MODE↦UPLOADING
            # Upload有两个回调：preUpload, upload_file
            self.Upload(file_path=file_path)
            return True
        else:
            # UP_MODE↦Normal/OverRide --> UP_MODE
            self.trigger("Ret_UP_MODE")
            return False

    def preUpload(self, event):
        """
        客户端上传前预备工作：告诉服务器我要开始发送了
        状态转换：UP_MODE --> UP_MODE↦UPLOADING
        """
        self.__sendmsg(pkg_type.FILE_UPLD, 5, {"token": f"{self.token}"}, recv=False)

    def upload_file(self, event: EventData):
        """
        进入 UP_MODE↦UPLOADING 状态的回调
        实现 上传文件 的逻辑
        :param event: 一些相关参数可以从这个变量获取
        :return: 返回到 UP_MODE 状态
        """
        if self.file_sock is None:    # 上传文件sock初始化
            self.file_sock = socket.create_connection((SERVER_HOST, 33333))  # TODO: 更改端口号
            self.file_sock = self.context.wrap_socket(self.file_sock, server_hostname=SERVER_HOST)
        file_path = event.kwargs.get("file_path")
        with open(file_path, "rb") as f:
            # TODO: [分段发送，进度显示]
            self.file_sock.sendall(f.read())  # 大文件可能一次传不完, 需要用sendall 或者 手动选择进度
            f.close()
        self.FinishUpload()

    def UpDone(self, event):
        """
        退出 UP_MODE↦UPLOADING 回调
        收到服务器接收完毕数据包，清空上传文件中的变量
        """
        # self.work_sock.send(sftp_msg(pkg_type.FILE_UPLD, 6, json.dumps({"token": f"{self.token}"})).pack())
        self.__recvmsg(pkg_type.FILE_UPLD)
        # 重置相关变量
        self.file_sock.close()
        del self.file_sock
        self.file_sock = None

    def reqDownloadFile(self, event):
        """
        下载文件
        Running子状态转换：DOWN_MODE --> DOWN_MODE↦DOWNLOADing (if return True)
        """
        # 查询服务器有哪些文件
        ack, msg = self.__sendmsg(pkg_type.SHOW_LIST, 0, {"token": self.token}, recv=True)
        msg = json.loads(msg)
        if ack == 1:
            file_list = msg["result"]
            if len(file_list) is 0:
                print("No files in Remote dir")
                self.trigger("Ret_DOWN_MODE")
                return False
            print_msg("You can download the following list of files:", file_list)
            file_name = None
            # 下载的文件是否在服务器列表
            while file_name not in file_list:
                file_name = input("Enter the file name you want to download: ")
                if file_name is 'q':
                    self.trigger("Ret_DOWN_MODE")
                    return False
            # 判断是否跟本地文件冲突, 并提示用户选择
            if file_name in get_local_dir():
                print(f"{file_name} exists in the local file")
                choice = input("override or no? (Y/N, default Y) >>> ")
                if choice is 'N':
                    self.trigger("Ret_DOWN_MODE")
                    return False
                else:
                    os.remove(LOCAL_DIR+file_name)
                    print(f"{file_name} in local dir has removed")
            # 进入下载过程
            self.Download(file_name=file_name)
        else:
            print("Server error, cannot download")
            self.trigger("Ret_DOWN_MODE")
            return False

    def preDownload(self, event):
        if self.down_conn_sock is None:
            self.down_listen_sock
        pass

    def download_file(self, event):
        pass

    def DownDone(self, event):
        pass


if __name__ == '__main__':
    my_client = STFP_Client(SERVER_URI, True)
    my_client.work()
