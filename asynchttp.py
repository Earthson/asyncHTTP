#!/usr/bin/env python

import types
from tornado import httpclient
from http.client import HTTPMessage, HTTPResponse

from http.cookiejar import MozillaCookieJar, DefaultCookiePolicy
import urllib.request

from tornado.ioloop import IOLoop
io_loop = IOLoop.instance()


class TmpResponse(object):
    '''hacking with info method'''
    def __init__(self, info):
        self._info = info

    def info(self):
        return self._info


def req_gen(*args, **kwargs):
    return httpclient.HTTPRequest(*args, **kwargs)


def nothing():
    pass


def client_gen(http_client, task_start=nothing, task_end=nothing):
    def sender_gen(cj, proxy=None):
        #cj.save(ignore_discard=True, ignore_expires=True)
        try:
            #try load file
            cj.load(ignore_discard=True, ignore_expires=True)
        except:
            #File May not exist
            pass
        def sender(req, callback):
            if isinstance(req, str):
                req = httpclient.HTTPRequest(req, request_timeout=5, max_redirects=10, use_gzip=True)
                req.headers = {
                        "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                        "User-Agent":'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/29.0.1547.57 Safari/537.36',
                        }
            oreq = urllib.request.Request(req.url)
            proxy_host=None if proxy is None else proxy[0]
            proxy_port=None if proxy is None else proxy[1]
            cj.add_cookie_header(oreq)
            req.headers.update(oreq.header_items())
            def callback_gen(callback):
                def func(response):
                    try:
                        responseinfo = HTTPMessage()
                        for k, v in response.headers.items():
                            responseinfo[k] = v
                        tmpresponse = TmpResponse(responseinfo)
                        cj.extract_cookies(tmpresponse, oreq)
                        callback(response)
                        #cj.save(ignore_discard=True, ignore_expires=True)

                        #tell taskmanager that the task have been done
                    finally:
                        task_end()
                        print("finish:", response.request.url)
                return func
            #try to start task, taskmanager may block here for limiting connection:)
            task_start()
            http_client.fetch(req, callback=callback_gen(callback))
        return sender
    return sender_gen



import threading
import time

__conn_count = 0
__conn_lock = threading.Lock()

def tasker_start(limit=1000):
    def func():
        global __conn_count, __conn_lock
        while __conn_count > limit:
            time.sleep(1)
        __conn_lock.acquire()
        __conn_count += 1
        __conn_lock.release()
    return func


def tasker_end():
    def func():
        global __conn_count, __conn_lock
        __conn_lock.acquire()
        __conn_count -= 1
        __conn_lock.release()
    return func


class httpTask(tuple):
    def __new__(self, *args):
        return tuple.__new__(self, args)


class AResult(tuple):
    def __new__(self, *res):
        return tuple.__new__(self, res)


from queue import Queue

class ahttpManager(object):

    def __init__(self, on_exit=[]):
        self.task_q = Queue()
        self.todo_at_exit = on_exit


    def on_exit_append(self, *args):
        self.todo_at_exit.extend(args)

    def task_alloc(self):
        while True:
            try:
                x = self.task_q.get(timeout=100)
                x[0](*x[1:])
            except Exception as e:
                print(e)
                print("no task in queue, exit now!")
                io_loop.stop()
                exit(0)


    def start_task_alloc(self):
        task_th = threading.Thread(target=self.task_alloc)
        task_th.daemon = True
        task_th.start() 


    def gen(self, callback):
        def ifunc(response):
            g = callback(response)
            res = []
            def get_res():
                #print("pass result:", res)
                return res
            if not isinstance(g, types.GeneratorType):
                res.append(g)
                return get_res
            def new_task(t):
                def icallback_gen(func):
                    tmp = self.gen(func)
                    def icallback(response):
                        m = tmp(response)
                        go_through(AResult(*m()))
                    return icallback
                tocall = icallback_gen(t[2])
                print("add:", t[1].url, tocall)
                self.add_task(t[0], t[1], icallback_gen(t[2]))
            def go_through(it=None):
                try:
                    e = g.send(it)
                    if type(e) == httpTask:
                        new_task(e)
                    else:
                        res.append(e)
                except StopIteration as ex:
                    pass
            go_through()
            return get_res
        return ifunc

    def add_task(self, sender, url, callback):
        self.task_q.put((sender, url, callback))

    def reg_task(self, sender, url):
        def func(callback):
            def ifunc(response):
                ans = callback(response)
                if ans is not None:
                    for e in ans:
                        self.add_task(sender, *e)
            self.add_task(sender, url, ifunc)
            return ifunc
        return func

    def async_run(self):
        self.start_task_alloc()
        io_loop.start()
        for each in self.todo_at_exit:
            each()

ahttp_mgr = ahttpManager()

def get_senders(mac_cnt=50, proxys=None, extra_cookie=None):
    fnames = ["cookies/%s.cookie" % i for i in range(mac_cnt)]
    maccookies = [MozillaCookieJar(e, policy=DefaultCookiePolicy(rfc2965=True)) for e in fnames]
    if extra_cookie is not None:
        for each in maccookies:
            each.set_cookie(extra_cookie)
    async_client = client_gen(httpclient.AsyncHTTPClient(), task_start=tasker_start(), task_end=tasker_end())
    if proxys is not None:
        mysenders = [async_client(e, p) for e, p in zip(maccookies, proxys)]
    else:
        mysenders = [async_client(e) for e in maccookies]
    def save_cookies():
        for each in maccookies:
            each.save()
    ahttp_mgr.on_exit_append(save_cookies)
    return mysenders


