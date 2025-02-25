import os
import json
import logging
from typing import Dict, List, Any, Optional

from models import (
    TaskDefinition, TaskType, ResourceConfig, RetryConfig, 
    TaskDependency, WorkflowConfiguration, WorkflowMetadata,
    BranchingConfig, ValidationConfig
)

class WorkflowParser:
  
    
    def __init__(self, config_path: str):
        
        self.logger = logging.getLogger(self.__class__.__name__)
        self.config_path = config_path
        self.raw_config = self._load_config()
        self.workflow_config = self._parse_workflow()
    
    def _load_config(self) -> Dict[str, Any]:
     
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            self.logger.error(f"Configuration file not found: {self.config_path}")
            raise
        except json.JSONDecodeError:
            self.logger.error(f"Invalid JSON in configuration file: {self.config_path}")
            raise
    
    def _parse_workflow(self) -> WorkflowConfiguration:
     
        metadata_data = self.raw_config.get('metadata', {})
        metadata = WorkflowMetadata(
            name=metadata_data.get('name', 'Unnamed Workflow'),
            description=metadata_data.get('description'),
            version=metadata_data.get('version', '1.0'),
            owner=metadata_data.get('owner'),
            project=metadata_data.get('project'),
            environment=metadata_data.get('environment'),
            tags=metadata_data.get('tags', [])
        )
        
        tasks = self._parse_tasks(self.raw_config.get('tasks', []))
        
        return WorkflowConfiguration(
            metadata=metadata,
            tasks=tasks,
            global_config=self.raw_config.get('global_config'),
            workflow_settings=self.raw_config.get('workflow_settings'),
            monitoring=self.raw_config.get('monitoring'),
            security=self.raw_config.get('security'),
            compliance=self.raw_config.get('compliance')
        )
    
    def _parse_tasks(self, raw_tasks: List[Dict[str, Any]]) -> List[TaskDefinition]:
      
        tasks = []
        
        for task_data in raw_tasks:
            try:
                task = self._parse_single_task(task_data)
                tasks.append(task)
            except Exception as e:
                self.logger.warning(f"Could not parse task {task_data.get('id', 'unknown')}: {e}")
        
        return tasks
    
    def _parse_single_task(self, task_data: Dict[str, Any]) -> TaskDefinition:
   
        required_fields = ['id', 'name', 'type', 'command']
        for field in required_fields:
            if field not in task_data:
                raise ValueError(f"Missing required field: {field}")
        
        try:
            task_type = TaskType[task_data['type'].upper()]
        except KeyError:
            raise ValueError(f"Unsupported task type: {task_data['type']}")
        
        dependencies = self._parse_dependencies(task_data.get('dependencies', []))
        
        retry_config = self._parse_retry_config(task_data.get('retry_config'))
        
        resources = self._parse_resource_config(task_data.get('resources'))
        
        branching = self._parse_branching_config(task_data.get('branching'))
        
        validation = self._parse_validation_config(task_data.get('validation'))
        
        return TaskDefinition(
            id=task_data['id'],
            name=task_data['name'],
            type=task_type,
            command=task_data['command'],
            function_name=task_data.get('function_name'),
            description=task_data.get('description'),
            args=task_data.get('args', {}),
            environment_vars=task_data.get('environment_vars', {}),
            dependencies=dependencies,
            retry_config=retry_config,
            resources=resources,
            branching=branching,
            validation=validation,
            timeout=task_data.get('timeout'),
            advanced_config=task_data.get('advanced_config'),
            tags=task_data.get('tags', []),
            log_output=task_data.get('log_output', True)
        )
    
    def _parse_dependencies(self, dependencies_data: List[Any]) -> List[TaskDependency]:
      
        dependencies = []
        for dep in dependencies_data:
            dependencies.append(
                TaskDependency(
                    task_id=dep if isinstance(dep, str) else dep.get('task_id'),
                    condition=dep.get('condition') if isinstance(dep, dict) else None
                )
            )
        return dependencies
    
    def _parse_retry_config(self, retry_data: Optional[Dict[str, Any]]) -> Optional[RetryConfig]:
     
        if not retry_data:
            return None
        
        return RetryConfig(
            max_attempts=retry_data.get('max_attempts', 3),
            delay_between_attempts=retry_data.get('delay_between_attempts', 30),
            backoff_strategy=retry_data.get('backoff_strategy', 'linear'),
            allowed_exceptions=retry_data.get('allowed_exceptions', [])
        )
    
    def _parse_resource_config(self, resources_data: Optional[Dict[str, Any]]) -> Optional[ResourceConfig]:
   
        if not resources_data:
            return None
        
        return ResourceConfig(
            cpu=resources_data.get('cpu'),
            memory=resources_data.get('memory'),
            gpu=resources_data.get('gpu', False),
            network_required=resources_data.get('network', False),
            container_config=resources_data.get('container_config')
        )
    
    def _parse_branching_config(self, branching_data: Optional[Dict[str, Any]]) -> Optional[BranchingConfig]:
      
        if not branching_data:
            return None
        
        return BranchingConfig(
            on_success=branching_data.get('on_success'),
            on_failure=branching_data.get('on_failure')
        )
    
    def _parse_validation_config(self, validation_data: Optional[Dict[str, Any]]) -> Optional[ValidationConfig]:
 
        if not validation_data:
            return None
        
        return ValidationConfig(
            min_file_size=validation_data.get('min_file_size'),
            max_file_size=validation_data.get('max_file_size'),
            required_content_checks=validation_data.get('required_content_checks', []),
            data_quality_checks=validation_data.get('data_quality_checks', [])
        )
    
    def validate_task_dependencies(self) -> bool:
    
        task_ids = {task.id for task in self.workflow_config.tasks}
        
        for task in self.workflow_config.tasks:
            for dep in task.dependencies:
                if dep.task_id not in task_ids:
                    self.logger.error(f"Invalid dependency: {dep.task_id} not found")
                    return False
        
        return True

def main():
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    config_path = 'sample.json'
    
    try:
        parser = WorkflowParser(config_path)
        
        if parser.validate_task_dependencies():
            print("Task dependencies validated successfully")
        
        print("\nWorkflow Metadata:")
        metadata = parser.workflow_config.metadata
        print(f"Name: {metadata.name}")
        print(f"Description: {metadata.description}")
        print(f"Version: {metadata.version}")
        
        print("\nParsed Tasks:")
        for task in parser.workflow_config.tasks:
            print(f"\nTask ID: {task.id}")
            print(f"Name: {task.name}")
            print(f"Type: {task.type}")
            print(f"Command: {task.command}")
            
            if task.dependencies:
                print("Dependencies:")
                for dep in task.dependencies:
                    print(f"  - {dep.task_id}")
    
    except Exception as e:
        print(f"Error processing workflow configuration: {e}")

if __name__ == '__main__':
    main()