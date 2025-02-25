import logging
import threading
import sqlite3
from parser import WorkflowParser
from workflow_engine import WorkflowEngine
from scheduler import WorkflowScheduler

DB_PATH = "tasks.db"

def load_pending_tasks(parser, scheduler):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        # Load scheduled tasks
        cursor.execute("SELECT task_id, run_at FROM scheduled_tasks")
        for task_id, run_at in cursor.fetchall():
            task = next((t for t in parser.workflow_config.tasks if t.id == task_id), None)
            if task:
                scheduler.task_queue.append(ScheduledTask(task, datetime.fromisoformat(run_at)))

        # Load failed tasks
        cursor.execute("SELECT task_id FROM failed_tasks")
        failed_tasks = [row[0] for row in cursor.fetchall()]
        scheduler.failed_tasks = {task_id: datetime.now() for task_id in failed_tasks}

def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    config_path = 'sample.json' 
    parser = WorkflowParser(config_path)

    if not parser.validate_task_dependencies():
        logging.error("Invalid task dependencies detected in configuration")
        return

    scheduler = WorkflowScheduler(parser.workflow_config)

    # Load tasks from the database
    load_pending_tasks(parser, scheduler)

    # Start the scheduler
    scheduler_thread = threading.Thread(target=scheduler.run, daemon=True)
    scheduler_thread.start()

if __name__ == '__main__':
    main()
