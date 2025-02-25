import time
import heapq
import logging
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from croniter import croniter

from models import TaskDefinition, WorkflowConfiguration
from workflow_engine import WorkflowEngine
from task_executor import TaskExecutionError

DB_PATH = "tasks.db"

class ScheduledTask:
   
    def __init__(self, task: TaskDefinition, run_at: datetime, priority: int):
        self.task = task
        self.run_at = run_at
        self.priority = priority

    def __lt__(self, other):
        return (self.run_at, -self.priority) < (other.run_at, -other.priority)

class WorkflowScheduler:
   
    def __init__(self, workflow_config: WorkflowConfiguration, cooldown_hours: int = 24):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.workflow_config = workflow_config
        self.engine = WorkflowEngine()
        self.task_queue: List[ScheduledTask] = []
        self.failed_tasks: Dict[str, datetime] = {}  
        self.cooldown_period = timedelta(hours=cooldown_hours)
        self.lock = threading.Lock()
        self.max_parallel_tasks = workflow_config.workflow_settings.get("execution_mode", {}).get("max_parallel_tasks", 1)
        self._init_db()

    def _init_db(self):
        
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_tasks (
                    task_id TEXT PRIMARY KEY,
                    run_at TEXT,
                    priority INTEGER,
                    status TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS failed_tasks (
                    task_id TEXT PRIMARY KEY,
                    retry_time TEXT
                )
            """)
            conn.commit()

    def schedule_tasks(self):
        
        now = datetime.now()
        for task in self.workflow_config.tasks:
            priority = task.advanced_config.get("priority", 1)
            schedule_info = task.advanced_config.get("schedule") if task.advanced_config else None
            if schedule_info:
                cron_expression = schedule_info.get("cron")
                if cron_expression:
                    next_run = self._get_next_cron_time(cron_expression)
                    self._save_task_to_db(task.id, next_run, priority, "scheduled")
                    heapq.heappush(self.task_queue, ScheduledTask(task, next_run, priority))
                    self.logger.info(f"Task {task.id} scheduled at {next_run} with priority {priority}")

    def run(self):
        
        while True:
            with self.lock:
                now = datetime.now()

       
                self._retry_failed_tasks(now)


                self._execute_parallel_tasks()

            time.sleep(10)  

    def _execute_parallel_tasks(self):
       
        available_workers = self.max_parallel_tasks
        futures = []
        executor = ThreadPoolExecutor(max_workers=available_workers)

        while self.task_queue and available_workers > 0:
            scheduled_task = heapq.heappop(self.task_queue)
            if scheduled_task.run_at <= datetime.now():
                futures.append(executor.submit(self._execute_task, scheduled_task.task))
                available_workers -= 1

   
        for future in as_completed(futures):
            future.result()

    def _execute_task(self, task: TaskDefinition):
       
        self.logger.info(f"Executing scheduled task: {task.id}")

        try:
            result = self.engine.run_workflow(self.workflow_config)
            if result.get(task.id, {}).get("status") == "failed":
                raise TaskExecutionError(
                    task.id, "ExecutionFailed", "Task failed and will be put in cooldown.", ""
                )
            self.logger.info(f"Task {task.id} completed successfully.")
            self._remove_task_from_db(task.id)

        except TaskExecutionError as e:
            self.logger.error(f"Task {task.id} failed: {str(e)}")
            retry_time = datetime.now() + self.cooldown_period
            self._save_failed_task_to_db(task.id, retry_time)
            self.logger.info(f"Task {task.id} put in cooldown until {retry_time}")

    def _retry_failed_tasks(self, now: datetime):
       
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT task_id FROM failed_tasks WHERE retry_time <= ?", (now,))
            retryable_tasks = [row[0] for row in cursor.fetchall()]

            for task_id in retryable_tasks:
                self.logger.info(f"Retrying task {task_id} after cooldown.")
                task = next((t for t in self.workflow_config.tasks if t.id == task_id), None)
                if task:
                    heapq.heappush(self.task_queue, ScheduledTask(task, now, task.advanced_config.get("priority", 1)))
                cursor.execute("DELETE FROM failed_tasks WHERE task_id = ?", (task_id,))
            conn.commit()

    def _get_next_cron_time(self, cron_expr: str) -> datetime:
       

        now = datetime.now()
        cron = croniter(cron_expr, now)
        return cron.get_next(datetime)

    def _save_task_to_db(self, task_id: str, run_at: datetime, priority: int, status: str):
        
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO scheduled_tasks (task_id, run_at, priority, status) VALUES (?, ?, ?, ?)",
                           (task_id, run_at.isoformat(), priority, status))
            conn.commit()

    def _save_failed_task_to_db(self, task_id: str, retry_time: datetime):
     
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO failed_tasks (task_id, retry_time) VALUES (?, ?)",
                           (task_id, retry_time.isoformat()))
            conn.commit()

    def _remove_task_from_db(self, task_id: str):
     
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM scheduled_tasks WHERE task_id = ?", (task_id,))
            conn.commit()
