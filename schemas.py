from enum import Enum
from typing import List, Optional, Dict, Any, TypedDict
from pydantic import BaseModel, Field

class ActionType(str, Enum):
    NAVIGATE = "navigate"
    CLICK = "click"
    FILL = "fill"
    SELECT = "select"
    CHECK = "check"
    ASSERT_TEXT = "assert_text"
    WAIT_FOR_SELECTOR = "wait_for_selector"

class TestStep(BaseModel):
    step_id: int
    description: str
    action_type: ActionType
    selector: Optional[str] = None
    selector_type: str = "css"  # css, xpath, role, text
    value: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    status: str = "pending"  # pending, passed, failed, healed
    error_message: Optional[str] = None

class AgentState(TypedDict):
    url: str
    task_goal: str
    current_step_index: int
    steps: List[TestStep]
    accessibility_snapshot: Optional[Dict[str, Any]]
    last_error: Optional[str]
    console_logs: List[str]
    failed_network_requests: List[str]
    is_complete: bool
    test_passed: bool
