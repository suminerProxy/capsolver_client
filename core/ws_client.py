import asyncio
import os
import sys

import websockets
import json
import yaml
import importlib
import concurrent.futures
from framework.solver_core import get_solver_config
from core.system_resources import auto_concurrency
from common.logger import get_logger,emoji
import traceback
logger = get_logger("ws_client")
with open("config/config.yaml", "r") as f:
    config = yaml.safe_load(f)

MAX_CONCURRENCY = config.get("concurrency") or auto_concurrency()
task_queue = asyncio.Queue()
semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
executor = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_CONCURRENCY)

logger.info(emoji("TASK",f"最大允许线程数:{MAX_CONCURRENCY}"))
def safe_import_handler(module_name: str, filename: str):
    try:
        logger.debug(f"🔍 正在尝试导入模块: task_handlers.{module_name}")
        return importlib.import_module(f"task_handlers.{module_name}")
    except ModuleNotFoundError as e:
        logger.warning(f"⚠️ 模块未找到（importlib 尝试失败）: {e}")
    except Exception as e:
        logger.error(f"❌ 使用 importlib 导入模块失败: {e}")
        logger.debug(traceback.format_exc())

    try:
        path = os.path.join("task_handlers", filename)
        logger.debug(f"🔍 尝试通过路径加载模块: {path}")

        if not os.path.exists(path):
            logger.error(f"❌ 文件不存在: {path}")
            return None

        spec = importlib.util.spec_from_file_location(module_name, path)
        if not spec:
            logger.error("❌ 创建模块 spec 失败")
            return None

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        try:
            spec.loader.exec_module(module)
        except Exception as e:
            logger.error(f"❌ 执行模块失败: {e}")
            logger.debug(traceback.format_exc())
            return None

        logger.info(f"✅ 成功通过路径加载模块: {module_name}")
        return module

    except Exception as e:
        logger.error(f"❌ 路径导入异常: {e}")
        logger.debug(traceback.format_exc())
        return None
async def run_task(task,proxy):
    module_name = task["type"]
    filename = f"{module_name}.py"
    handler = safe_import_handler(module_name, filename)
    logger.debug(f"执行的函数:{handler}")
    if asyncio.iscoroutinefunction(handler.run):
        result = await handler.run(task,proxy)
        while asyncio.iscoroutine(result):
            result = await result
        return result
    else:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, handler.run, task)

async def task_worker(ws):
    while True:
        task,proxy = await task_queue.get()
        async with semaphore:
            try:
                result = await run_task(task,proxy)
                await ws.send(json.dumps({
                    "type": "task_result",
                    "taskId": task["taskId"],
                    "errorId": 0,
                    "result": result
                }))
            except Exception as e:
                await ws.send(json.dumps({
                    "type": "task_result",
                    "taskId": task.get("taskId"),
                    "errorId":-1,
                    "result": {"error": str(e)}
                }))
        task_queue.task_done()

async def heartbeat(ws):
    while True:
        running_tasks = MAX_CONCURRENCY - semaphore._value
        waiting_tasks = task_queue.qsize()
        msg = {"type": "status_update", "current_tasks": running_tasks+waiting_tasks, "pending_tasks": running_tasks}
        await ws.send(json.dumps(msg))
        await asyncio.sleep(10)

async def receiver(ws):
    while True:
        msg = await ws.recv()
        task = json.loads(msg).get("task")
        proxy = json.loads(msg).get("proxy")
        logger.info(emoji("GETTASK",f"接收到任务: {task['type']} - {task['taskId']}"))
        await task_queue.put((task,proxy))


async def worker_main():
    uri = config.get("worker").get("wss_url") + config.get("worker").get("name")

    while True:
        try:
            async with websockets.connect(uri) as ws:
                await ws.send(json.dumps({
                    "type": "register",
                    "task_types": get_solver_config().get("solver_type"),
                    "max_concurrency": MAX_CONCURRENCY
                }))
                logger.info(emoji("SUCCESS", f"已注册: {uri}"))

                # ✅ 用手动方式创建任务列表
                tasks = []
                tasks.append(asyncio.create_task(heartbeat(ws)))
                tasks.append(asyncio.create_task(receiver(ws)))
                for _ in range(MAX_CONCURRENCY):
                    tasks.append(asyncio.create_task(task_worker(ws)))

                # 等待任务完成（或直到其中一个挂掉）
                await asyncio.gather(*tasks)

        except Exception as e:
            logger.warning(emoji("ERROR", f"连接断开: {e}"))

        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(5)