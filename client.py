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
        self.up_sock = None     # 上传文件专用socket
        self.down_sock = None   # 下载文件专用socket
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
                "before": "sendUpDone"
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
        print('Welcome SFTP System')    # 打印欢迎语
        while True:
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

    def reqSignUp(self, event):
        """
        注册逻辑实现
        状态转换：Init -> SignUpSuccess (if return True)
        """
        # 获取用户输入
        usr_name = input('>>>username:')
        passwd = getpass.getpass('>>>password:')
        # print(usr_name, passwd)

        # 组装SignUp数据包
        signUpMsg = json.dumps({
            "name": usr_name,
            "pwd": passwd
        })
        pkg = sftp_msg(pkg_type.SignUp, 0, signUpMsg).pack()

        try:
            # 发送SignUp数据包
            nSent = self.work_sock.send(pkg)
            print(f"发送字节数:{nSent}")
            ret_pkg = self.work_sock.recv(BUFFER_SIZE)  # 接收返回的数据包
            # print(ret_pkg)
            if ret_pkg is None:
                print("服务器错误")
                return False
            ptype, ack, length, msg = sftp_msg.unpack(ret_pkg)  # 拆包
            assert ptype == pkg_type.SignUp
            print(msg)
            return True if ack is 1 else False

        except ConnectionResetError as e:
            print('服务器掉线，注册失败')
            return False

    def reqSignIn(self, event):
        """
        登录逻辑实现
        状态转换：Init -> Running (if return True)
        """
        # TODO: 注册，登录代码优化
        usr_name = input('>>>username:')
        # passwd = getpass.getpass('>>>password:')
        passwd = input('>>>password:')
        signInMsg = json.dumps({
            "name": usr_name,
            "pwd": passwd
        })
        pkg = sftp_msg(pkg_type.SignIn, 0, signInMsg).pack()
        try:
            # 发送SignIn数据包
            nSent = self.work_sock.send(pkg)
            print(f"发送字节数:{nSent}")
            ret_pkg = self.work_sock.recv(BUFFER_SIZE)  # 接收返回的数据包
            # print(ret_pkg)
            if ret_pkg is None:
                print("服务器错误")
                return False
            ptype, ack, length, msg = sftp_msg.unpack(ret_pkg)  # 拆包
            # assert ptype == pkg_type.SignIn
            msg = json.loads(msg)
            print(msg)
            if ack is 1:
                self.token = msg['token']
                return True
            else:
                return False

        except ConnectionResetError as e:
            print('服务器掉线，登录失败')
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
        print("token:", self.token)

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
        pkg = sftp_msg(pkg_type.SignOut, 0, json.dumps({"token": self.token})).pack()
        nSend = self.work_sock.send(pkg)
        print(f"发送字节数:{nSend}")

    def reqRemoteDir(self, event):
        """
        显示远程目录
        内部状态转换：Running↦LS_MODE
        """
        pass

    def reqLocalDir(self, event):
        """
        显示本地目录
        内部状态转换：Running↦LS_MODE
        """
        if not os.path.exists(LOCAL_DIR):
            os.mkdir(LOCAL_DIR)
        file_list = os.listdir(LOCAL_DIR)
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
                return False
        assert os.path.exists(file_path)
        # 发送 文件上传请求 数据包
        pkg_msg = json.dumps({
            "filename": os.path.basename(file_path),
            "filesize": os.path.getsize(file_path),
            "token": self.token
        })
        self.work_sock.send(
            sftp_msg(pkg_type.FILE_UPLD, mode, pkg_msg).pack()
        )
        # 接收 返回的数据包
        ret_pkg = self.work_sock.recv(BUFFER_SIZE)
        if ret_pkg is None:
            print("服务器错误")
            return False
        ptype, ack, length, msg = sftp_msg.unpack(ret_pkg)  # 拆包
        msg = json.loads(msg)
        print(msg)
        if ack == 2:
            # 如果服务器端合适，手动触发状态转换
            # UP_MODE --> UP_MODE↦Upload
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
        状态转换：UP_MODE --> UP_MODE↦Upload
        """
        self.work_sock.send(sftp_msg(pkg_type.FILE_UPLD, 5, json.dumps({"token": f"{self.token}"})).pack())

    def upload_file(self, event: EventData):
        """
        进入 UP_MODE↦Upload 状态的回调
        实现 上传文件 的逻辑
        :param event: 一些相关参数可以从这个变量获取
        :return: 返回到 UP_MODE 状态
        """
        if self.up_sock is None:
            self.up_sock = socket.create_connection((SERVER_HOST, 33333))  # TODO: 更改端口号
            self.up_sock = self.context.wrap_socket(self.up_sock, server_hostname=SERVER_HOST)
        file_path = event.kwargs.get("file_path")
        with open(file_path, "rb") as f:
            self.up_sock.sendall(f.read())  # 大文件可能一次传不完
            f.close()
        self.FinishUpload()

    def sendUpDone(self, event):
        """
        状态转换：UP_MODE↦UPLOADING -> UP_MODE
        收到服务器接收完毕数据包，清空上传文件中的变量
        """
        # self.work_sock.send(sftp_msg(pkg_type.FILE_UPLD, 6, json.dumps({"token": f"{self.token}"})).pack())
        ret_pkg = self.work_sock.recv(BUFFER_SIZE)
        ptype, ack, length, msg = sftp_msg.unpack(ret_pkg)  # 拆包
        msg = json.loads(msg)
        print(msg)
        # 重置相关变量
        self.up_sock.close()
        del self.up_sock
        self.up_sock = None

    def reqDownloadFile(self, event):
        """
        下载文件
        内部状态转换：Running↦DOWN_MODE
        """
        pass


if __name__ == '__main__':
    my_client = STFP_Client(SERVER_URI, True)
    my_client.work()