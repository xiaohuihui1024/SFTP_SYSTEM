import pymysql
import logging


# 数据库测试
class MySQLHelper(object):
    def __init__(self, password, database, host="localhost", port=3306, charset='utf8', user="root"):
        # 初始化参数
        self.__host = host
        self.__port = port
        self.__password = password
        self.__database = database
        self.__charset = charset
        self.__user = user
        # 连接数据库
        self.db = pymysql.connect(host=self.__host, port=self.__port, user=self.__user, password=self.__password,
                                  database=self.__database, charset=self.__charset)
        # 使用 cursor() 方法创建一个游标对象 cursor
        # 以字典形式返回数据，即返回的list中，每一项为dict
        self.__cur = self.db.cursor(cursor=pymysql.cursors.DictCursor)
        # print(self.conn)

    def test(self):
        self.__cur.execute("SELECT VERSION()")
        data = self.__cur.fetchone()
        print("Database version : %s " % data)

    def insert(self, table, datas):
        '''
        动态插入数据
        :param table: 表名
        :param datas: 字典形式的数据，跟数据库保持一致
        :return: True->成功
        '''
        # table = 'user'
        # dictData = {'id': '1001', 'name': 'zhangsan', 'age': '17'}
        keys = ','.join(datas.keys())
        values = ','.join(['%s'] * len(datas))
        sql = f'INSERT INTO {table}({keys})VALUES({values})'
        try:
            if self.__cur.execute(sql, tuple(datas.values())):
                self.db.commit()
                return True
            else:
                return False
        except Exception as e:
            self.db.rollback()
            return False

    def update(self, table, new_datas:dict, old_datas:dict):
        '''
        更新数据
        :param table: 表名
        :param new_datas: 更新后的数据 dict
        :param old_datas: 查询条件 dict
        :return: True or None
        '''
        # 实例数据
        # data_dic = {'id': '1001', 'name': 'zhangsan', 'age': '17'}
        # table = 'name'
        # 逻辑
        new_sql = ','.join(['%s=%s' % (k, '%s') for k in new_datas.keys()])
        old_sql = ' and '.join(['%s=%s' % (k, '%s') for k in old_datas.keys()])
        sql = f'UPDATE {table} SET {new_sql} WHERE {old_sql}'
        try:
            # 防止SQL注入
            if self.__cur.execute(sql, tuple(list(new_datas.values()) + list(old_datas.values()))):
                # print('OK')
                # 提交事务(这个一定要主动提交，不然在数据库中操作增、删结果不改变)
                self.db.commit()
                return True
        except Exception as e:
            # 回滚
            self.db.rollback()

    def query(self, table,  column_names: list = None, cond=None):
        """
        查询数据
        :param table: 表名
        :param column_names: 查询的字段(list)，默认*
        :param cond: 查询条件
        :return: (datas, count)
        """
        if column_names is None:
            column_names = ["*"]
        columns = ','.join(column_names)
        sql = f'select {columns} from {table}'
        if cond:
            cond_sql = ' and '.join(['%s=%s' % (k, '%s') for k in cond.keys()])
            sql += f" WHERE {cond_sql}"
            count = self.__cur.execute(sql, tuple(cond.values()))
        else:
            count = self.__cur.execute(sql)
        assert count is not None
        # 返回全部数据, 数据总量
        return self.__cur.fetchall(), count

    def delete(self, table, cond: dict):
        '''
        数据库删除操作
        :param table: 表名
        :param cond: 查询条件，必须
        :return: True or None
        '''
        cond_sql = ' and '.join(['%s=%s' % (k, '%s') for k in cond.keys()])
        sql = f'delete from {table} where {cond_sql}'
        try:
            self.__cur.execute(sql, tuple(cond.values()))
            self.db.commit()
            return True
        except Exception as e:
            print(e)
            self.db.rollback()

    def __del__(self):
        self.__cur.close()
        self.db.close()
        print('db closed')


# TODO: 异常 or关键操作加入logger

if __name__ == '__main__':
    conn = MySQLHelper('FQhL&!24%)Aq', 'sftp_db')
    conn.test()
    conn.insert('user', {'username': 'zhangsan', 'salt': '*'*40, 'password': '@'*40})
    conn.insert('user', {'username': 'lisi', 'salt': '#'*40, 'password': '@'*40})
    conn.insert('user', {'username': 'wangwu', 'salt': '*'*40, 'password': '@'*40})
    conn.query('user', cond={'salt': '*'*40})
    conn.delete('user', cond={'username': 'wangwu'})
    conn.update('user', {'username': 'zhangsan', 'salt': '!'*40, 'password': '#'*40},
                {'username': 'zhangsan', 'password': '@'*40})

'''
参考：
https://juejin.im/post/5d0af5a76fb9a07ef161880f

Python3 Mysql连库及简单封装使用
https://xu3352.github.io/python/2018/05/22/python-mysql-usage
'''
