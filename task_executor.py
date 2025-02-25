import os
import sys
import time
import subprocess
import logging
import importlib.machinery
import traceback
from typing import Dict, Any, Optional, Callable

from models import TaskDefinition, TaskType, RetryConfig

class TaskExecutionError(Exception):
    def __init__(self, task_id: str, error_type: str, message: str, traceback_info: str):
        self.task_id = task_id
        self.error_type = error_type
        self.message = message
        self.traceback_info = traceback_info
        super().__init__(f"Task {task_id} failed: {error_type} - {message}\n{traceback_info}")

class TaskNotFoundError(TaskExecutionError):

    def __init__(self, task_id: str, missing_item: str, item_type: str):
        message = f"{item_type} '{missing_item}' not found for task {task_id}."
        super().__init__(task_id, "TaskNotFoundError", message, "")

class TaskDependencyError(TaskExecutionError):

    def __init__(self, task_id: str, missing_dependency: str):
        message = f"Dependency '{missing_dependency}' is missing or unmet for task {task_id}."
        super().__init__(task_id, "TaskDependencyError", message, "")

class TaskExecutor:
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(self.__class__.__name__)

    def execute_task(self, task: TaskDefinition, retry_callback: Optional[Callable] = None) -> Dict[str, Any]:
        execution_result = {
            'task_id': task.id,
            'status': 'pending',
            'start_time': time.time(),
            'end_time': None,
            'output': None,
            'error': None,
            'attempts': 0
        }
        retry_config = task.retry_config or RetryConfig()

        while execution_result['attempts'] < retry_config.max_attempts:
            try:
                execution_result['attempts'] += 1
                self.logger.info(f"Executing task {task.id}, Attempt {execution_result['attempts']}")

                if task.type == TaskType.SHELL:
                    output = self._execute_shell_task(task)
                elif task.type == TaskType.PYTHON:
                    output = self._execute_python_task(task)
                elif task.type == TaskType.CUSTOM:
                    output = self._execute_custom_task(task)
                else:
                    raise TaskExecutionError(task.id, "InvalidTaskType", f"Unsupported task type: {task.type}", "")

                execution_result.update({
                    'status': 'success',
                    'output': output,
                    'end_time': time.time()
                })
                return execution_result

            except Exception as e:
                error_details = {
                    'error_type': type(e).__name__,
                    'error_message': str(e),
                    'traceback': traceback.format_exc()
                }
                self.logger.error(f"Task {task.id} failed: {error_details}")

                self._log_failed_task(task, error_details)

                execution_result.update({
                    'status': 'failed',
                    'error': error_details,
                    'end_time': time.time()
                })

                if retry_config.allowed_exceptions and error_details['error_type'] not in retry_config.allowed_exceptions:
                    break

                if execution_result['attempts'] < retry_config.max_attempts:
                    retry_delay = self._calculate_retry_delay(retry_config, execution_result['attempts'])
                    self.logger.info(f"Retrying task {task.id} in {retry_delay} seconds")
                    time.sleep(retry_delay)

                if retry_callback:
                    retry_callback(task, execution_result)

        raise TaskExecutionError(task.id, "MaxRetriesExceeded", f"Task {task.id} failed after {execution_result['attempts']} attempts", "")

    def _execute_shell_task(self, task: TaskDefinition) -> str:
        env = os.environ.copy()
        env.update(task.environment_vars)
        result = subprocess.run(
            task.command,
            shell=True,
            capture_output=True,
            text=True,
            env=env,
            timeout=task.timeout
        )
        if result.returncode != 0:
            raise TaskExecutionError(task.id, "ShellExecutionFailed", result.stderr, "")
        return result.stdout.strip()

    def _execute_python_task(self, task: TaskDefinition) -> Any:
        script_path = os.path.abspath(task.command)
        if not os.path.exists(script_path):
            alternative_path = os.path.join(os.getcwd(), task.command)
            if os.path.exists(alternative_path):
                script_path = alternative_path
            else:
                raise TaskNotFoundError(task.id, task.command, "Python script")

        module_path = os.path.dirname(script_path)
        module_name = os.path.splitext(os.path.basename(script_path))[0]

        if module_path not in sys.path:
            sys.path.insert(0, module_path)

        try:
            loader = importlib.machinery.SourceFileLoader(module_name, script_path)
            module = loader.load_module()
            if task.function_name:
                if not hasattr(module, task.function_name):
                    raise TaskNotFoundError(task.id, task.function_name, "Function")
                target_func = getattr(module, task.function_name)
            else:
                target_func = self._find_default_function(module)
            return target_func(**task.args)
        finally:
            if module_path in sys.path:
                sys.path.remove(module_path)

    def _execute_custom_task(self, task: TaskDefinition) -> Any:
        raise TaskExecutionError(task.id, "CustomTaskNotImplemented", f"Custom task type not implemented for {task.id}", "")

    def _find_default_function(self, module):
        import inspect
        if hasattr(module, 'main') and callable(module.main):
            return module.main
        if hasattr(module, 'run') and callable(module.run):
            return module.run
        functions = [func for name, func in inspect.getmembers(module, inspect.isfunction)
                     if func.__module__ == module.__name__]
        if functions:
            return functions[0]
        raise TaskExecutionError("Unknown", "NoSuitableFunction", "No suitable function found in the module", "")

    def _calculate_retry_delay(self, retry_config: RetryConfig, attempt: int) -> float:
        base_delay = retry_config.delay_between_attempts
        if retry_config.backoff_strategy == 'linear':
            return base_delay * attempt
        elif retry_config.backoff_strategy == 'exponential':
            return base_delay * (retry_config.backoff_factor ** attempt)
        else:
            return base_delay

    def _log_failed_task(self, task: TaskDefinition, error_details: Dict[str, Any]):
 
        module_name = os.path.splitext(os.path.basename(task.command))[0]
        function_name = task.function_name or "default_function"
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        
        log_dir = os.path.join("failed_tasks", module_name)
        os.makedirs(log_dir, exist_ok=True)

        log_file = os.path.join(log_dir, f"{function_name}_{timestamp}.log")

        with open(log_file, "w") as f:
            f.write(f"Task ID: {task.id}\n")
            f.write(f"Function: {function_name}\n")
            f.write(f"Module: {module_name}\n")
            f.write(f"Error Type: {error_details['error_type']}\n")
            f.write(f"Error Message: {error_details['error_message']}\n")
            f.write(f"Traceback:\n{error_details['traceback']}\n")

        self.logger.info(f"Logged failed task {task.id} execution to {log_file}")
