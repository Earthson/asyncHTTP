#!/usr/bin/env python

conn_limit = 5000

from tornado import httpclient
from http.client import HTTPMessage, HTTPResponse

import http.cookiejar
import urllib.request

from tornado.ioloop import IOLoop
io_loop = IOLoop.instance()

class TmpResponse(object):
    '''hacking with info method'''
    def __init__(self, info):
        self._info = info

    def info(self):
        return self._info


def client_gen(http_client):
    def sender_gen(cj):
        #cj.save(ignore_discard=True, ignore_expires=True)
        try:
            #try load file
            cj.load(ignore_discard=True, ignore_expires=True)
        except:
            #File May not exist
            pass
        #print(cj.as_lwp_str())
        def sender(url, callback):
            oreq = urllib.request.Request(url)
            req = httpclient.HTTPRequest(url)
            cj.add_cookie_header(oreq)
            req.headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/29.0.1547.57 Safari/537.36",
            }
            req.headers.update(oreq.headers)
            def callback_gen(callback):
                def func(response):
                    responseinfo = HTTPMessage()
                    for k, v in response.headers.items():
                        responseinfo[k] = v
                    tmpresponse = TmpResponse(responseinfo)
                    cj.extract_cookies(tmpresponse, oreq)
                    ans = callback(response)
                    #cj.save(ignore_discard=True, ignore_expires=True)
                    count_q.get()
                    #print("CountQueueSize: ", count_q.qsize())
                    if count_q.empty():
                        print("#stop")
                        io_loop.stop()
                    return ans
                return func
            http_client.fetch(req, callback=callback_gen(callback))
        return sender
    return sender_gen


from queue import Queue

task_q = Queue()
count_q = Queue(conn_limit)
solution_q = Queue()

task_map = dict()

def reg_task(task_name):
    def wrapper(func):
        def ifunc(*args, **kwargs):
            count_q.put(True)
            return func(*args, **kwargs)
        task_map[task_name] = ifunc
        return ifunc
    return wrapper


def alloc_task():
    while True:
        x = task_q.get()
        task_map[x[0]](*x[1])

import random

def async_run(urls, machine_cnt=50, conn_cnt=300, extra_cookie=None):
    from threading import Thread
    fnames = ["cookies/%s.cookie" % i for i in range(machine_cnt)]
    maccookies = [http.cookiejar.LWPCookieJar(e) for e in fnames]
    if extra_cookie is not None:
        for each in maccookies:
            each.set_cookie(extra_cookie)

    async_client = client_gen(httpclient.AsyncHTTPClient())
    mysenders = [async_client(e) for e in maccookies]

    task_th = Thread(target=alloc_task)
    task_th.daemon = True
    task_th.start()

    print("generating task...")

    for i in range(conn_cnt):
        task_q.put(("Req", (random.choice(mysenders), random.choice(urls))))
    io_loop.start()
    for each in maccookies:
        each.save()


def get_solution():
    while not solution_q.empty():
        yield solution_q.get()
