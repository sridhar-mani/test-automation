from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Any, Optional

class TaskType(Enum):
    SHELL = auto()
    PYTHON = auto()
    CUSTOM = auto()

@dataclass
class ResourceConfig:
    cpu: Optional[float] = None
    memory: Optional[str] = None
    gpu: Optional[bool] = False
    network_required: bool = False
    container_config: Optional[Dict[str, Any]] = None

@dataclass
class RetryConfig:
    max_attempts: int = 3
    delay_between_attempts: int = 30  
    backoff_strategy: str = 'linear'
    allowed_exceptions: List[str] = field(default_factory=list)
    backoff_factor: float = 2.0

@dataclass
class TaskDependency:
  
    task_id: str
    condition: Optional[str] = None 

@dataclass
class BranchingConfig:

    on_success: Optional[str] = None
    on_failure: Optional[Dict[str, Any]] = None

@dataclass
class ValidationConfig:
    min_file_size: Optional[str] = None
    max_file_size: Optional[str] = None
    required_content_checks: List[str] = field(default_factory=list)
    data_quality_checks: List[str] = field(default_factory=list)

@dataclass
class TaskDefinition:

    id: str
    name: str
    type: TaskType
    command: str
    

    function_name: Optional[str] = None
    description: Optional[str] = None
    

    args: Dict[str, Any] = field(default_factory=dict)
    environment_vars: Dict[str, str] = field(default_factory=dict)
    

    dependencies: List[TaskDependency] = field(default_factory=list)
    retry_config: Optional[RetryConfig] = None
    branching: Optional[BranchingConfig] = None
    
    resources: Optional[ResourceConfig] = None
    timeout: Optional[float] = None 
    
    validation: Optional[ValidationConfig] = None
    
    advanced_config: Optional[Dict[str, Any]] = None
    
    tags: List[str] = field(default_factory=list)
    log_output: bool = True

@dataclass
class WorkflowMetadata:
    name: str
    description: Optional[str] = None
    version: str = '1.0'
    owner: Optional[str] = None
    project: Optional[str] = None
    environment: Optional[str] = None
    tags: List[str] = field(default_factory=list)

@dataclass
class WorkflowConfiguration:
    metadata: WorkflowMetadata
    tasks: List[TaskDefinition]
    global_config: Optional[Dict[str, Any]] = None
    workflow_settings: Optional[Dict[str, Any]] = None
    monitoring: Optional[Dict[str, Any]] = None
    security: Optional[Dict[str, Any]] = None
    compliance: Optional[Dict[str, Any]] = None