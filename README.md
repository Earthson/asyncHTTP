asyncHTTP
=========

asyncHTTP task framework with tornado, Python 3, cookiejar


### Usage


taskes are represented as tuple(task_type, arguments_to_proc_func)

arguments_to_proc_func is a tuple, it is passed to func proc by `proc(*arguments_to_proc_fun)`

```python
from asynchttp import reg_task, async_run


@reg_task("here_your_task_type")
def do_proc(sender, url):
    def callback(response):
        print(response.body)
    sender(url, callback=callback)

#Or just use reg_response for much more simple task
@reg_response("you_task_type")
def print_response_body(response):
    print(response.body)


#finally run function async_run
#this function blocked until all task has been done(if you do not add new task when all task has been done)
async_run(your_urls_here)
```
