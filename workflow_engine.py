import logging
from typing import Dict, Any, List

from models import WorkflowConfiguration, TaskDefinition
from task_executor import TaskExecutor, TaskExecutionError

class WorkflowEngine:
   
    def __init__(self, logger: logging.Logger = None):
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.executor = TaskExecutor(logger=self.logger)

    def run_workflow(self, workflow_config: WorkflowConfiguration) -> Dict[str, Any]:
       
        self.logger.info(f"Starting workflow: {workflow_config.metadata.name}")
        ordered_tasks = self._resolve_task_order(workflow_config.tasks)
        results = {}

        for task in ordered_tasks:
            # Check if all dependencies succeeded; if not, skip the task.
            if any(dep.task_id not in results or results[dep.task_id]['status'] != 'success'
                   for dep in task.dependencies):
                self.logger.info(f"Skipping task {task.id} due to unmet dependencies")
                results[task.id] = {'status': 'skipped', 'reason': 'Dependencies not met'}
                continue

            try:
                result = self.executor.execute_task(task)
                results[task.id] = result
            except TaskExecutionError as e:
                self.logger.error(f"Task {task.id} failed: {str(e)}")
                results[task.id] = {'status': 'failed', 'error': str(e)}

        self.logger.info("Workflow execution completed")
        return results

    def _resolve_task_order(self, tasks: List[TaskDefinition]) -> List[TaskDefinition]:
     
        task_dict = {task.id: task for task in tasks}
        in_degree = {task.id: 0 for task in tasks}
        graph = {task.id: [] for task in tasks}

        for task in tasks:
            for dep in task.dependencies:
                if dep.task_id in task_dict:
                    graph[dep.task_id].append(task.id)
                    in_degree[task.id] += 1

        queue = [task_id for task_id, degree in in_degree.items() if degree == 0]
        ordered_ids = []

        while queue:
            current = queue.pop(0)
            ordered_ids.append(current)
            for neighbor in graph[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(ordered_ids) != len(tasks):
            self.logger.error("Cycle detected in task dependencies")
            raise Exception("Cycle detected in task dependencies")

        return [task_dict[task_id] for task_id in ordered_ids]
