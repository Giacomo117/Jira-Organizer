from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone
import json
import aiohttp
from base64 import b64encode
from openai import AsyncOpenAI
import aiosqlite
import asyncio

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Database path
DB_PATH = ROOT_DIR / 'jira_organizer.db'

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== Database Setup ====================

async def init_db():
    """Initialize SQLite database with required tables"""
    async with aiosqlite.connect(DB_PATH) as db:
        # Jira configurations table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS jira_configs (
                id TEXT PRIMARY KEY,
                jira_domain TEXT NOT NULL,
                jira_email TEXT NOT NULL,
                jira_api_token TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        ''')

        # Meeting analyses table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS meeting_analyses (
                id TEXT PRIMARY KEY,
                jira_project_key TEXT NOT NULL,
                client_name TEXT NOT NULL,
                project_name TEXT NOT NULL,
                meeting_minutes TEXT NOT NULL,
                proposed_changes TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                processed_at TEXT
            )
        ''')

        await db.commit()
        logger.info(f"Database initialized at {DB_PATH}")

# ==================== Models ====================

class JiraConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    jira_domain: str  # e.g., "yourcompany.atlassian.net"
    jira_email: str
    jira_api_token: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class JiraConfigCreate(BaseModel):
    jira_domain: str
    jira_email: str
    jira_api_token: str

class JiraConfigTestRequest(BaseModel):
    jira_domain: str
    jira_email: str
    jira_api_token: str

class JiraConnectionTest(BaseModel):
    success: bool
    message: str

class ProposedTicket(BaseModel):
    action: str  # "create" or "modify"
    ticket_key: Optional[str] = None  # For modifications
    issue_type: str  # Epic, Story, Task, Subtask, Bug
    summary: str
    description: str
    story_points: Optional[int] = None  # 1,2,3,5,8,13
    priority: Optional[str] = None  # High, Medium, Low
    parent_summary: Optional[str] = None  # Parent Epic/Story title
    dependencies: Optional[List[str]] = None  # List of dependent issue summaries
    reasoning: str
    current_summary: Optional[str] = None  # For modifications
    current_description: Optional[str] = None  # For modifications

class MeetingAnalysis(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    jira_project_key: str
    client_name: str
    project_name: str
    meeting_minutes: str
    proposed_changes: List[ProposedTicket] = []
    status: str = "pending"  # pending, approved, rejected, partially_approved
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    processed_at: Optional[datetime] = None

class MeetingAnalysisCreate(BaseModel):
    jira_project_key: str
    client_name: str
    project_name: str
    meeting_minutes: str

class ApprovalRequest(BaseModel):
    approved_indices: List[int] = []  # Indices of proposals to approve
    rejected_indices: List[int] = []  # Indices of proposals to reject

class ModifyProposalRequest(BaseModel):
    index: int
    summary: Optional[str] = None
    description: Optional[str] = None

# ==================== Jira API Helper ====================

class JiraAPIClient:
    def _clean_domain(self, domain: str) -> str:
        """Clean and validate Jira domain"""
        # Remove protocol if present
        domain = domain.replace("https://", "").replace("http://", "")
        # Remove trailing slash if present
        domain = domain.rstrip("/")
        # Remove /rest/api/3 if present
        domain = domain.replace("/rest/api/3", "")
        
        # Validate domain format
        if not domain or domain.strip() == "":
            raise ValueError("Domain cannot be empty")
        
        return domain.strip()

    def __init__(self, domain: str, email: str, api_token: str):
        # Clean and validate domain
        logger.info(f"JiraAPIClient init - raw domain: '{domain}'")
        self.domain = self._clean_domain(domain)
        logger.info(f"JiraAPIClient init - cleaned domain: '{self.domain}'")
        self.base_url = f"https://{self.domain}/rest/api/3"
        logger.info(f"JiraAPIClient init - base_url: '{self.base_url}'")
        self.email = email
        self.api_token = api_token

        # Create basic auth header
        auth_str = f"{email}:{api_token}"
        auth_bytes = auth_str.encode('utf-8')
        auth_b64 = b64encode(auth_bytes).decode('ascii')

        self.headers = {
            "Authorization": f"Basic {auth_b64}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    async def test_connection(self) -> bool:
        """Test the connection to Jira"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/myself"
                logger.info(f"Testing Jira connection to: {url}")
                async with session.get(url, headers=self.headers) as response:
                    logger.info(f"Jira response status: {response.status}")
                    if response.status == 200:
                        response_text = await response.text()
                        logger.info(f"Jira connection successful, user info: {response_text[:200]}...")
                        return True
                    else:
                        response_text = await response.text()
                        logger.error(f"Jira connection failed with status {response.status}: {response_text[:200]}...")
                        return False
        except Exception as e:
            logger.error(f"Jira connection test failed: {e}")
            return False

    async def get_project_tickets(self, project_key: str) -> List[Dict[str, Any]]:
        """Fetch all tickets for a project"""
        try:
            all_tickets = []
            start_at = 0
            max_results = 100

            async with aiohttp.ClientSession() as session:
                while True:
                    jql = f"project = {project_key} ORDER BY created DESC"
                    
                    # Use the correct JQL search endpoint (migrated from deprecated /search)
                    payload = {
                        "jql": jql,
                        "startAt": start_at,
                        "maxResults": max_results,
                        "fields": ["summary", "description", "status", "issuetype", "key", "parent", "issuelinks"]
                    }

                    async with session.post(
                        f"{self.base_url}/search/jql",
                        headers=self.headers,
                        json=payload
                    ) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            logger.error(f"Failed to fetch tickets: {response.status} - {error_text}")
                            logger.error(f"Request payload: {payload}")
                            break

                        data = await response.json()
                        issues = data.get('issues', [])
                        all_tickets.extend(issues)

                        total = data.get('total', 0)
                        logger.info(f"Fetched {len(issues)} tickets, total available: {total}")

                        # Check if there are more results
                        if len(issues) < max_results or start_at + len(issues) >= total:
                            break

                        start_at += max_results

            return all_tickets
        except Exception as e:
            logger.error(f"Error fetching project tickets: {e}")
            return []



    async def get_hierarchical_structure(self, project_key: str) -> Dict[str, Any]:
        """Get project tickets organized by hierarchy (Epic -> Story -> Task/Subtask)"""
        try:
            all_tickets = await self.get_project_tickets(project_key)
            
            structure = {
                "epics": {},
                "stories": {},
                "tasks": {},
                "subtasks": {},
                "orphaned": []
            }
            
            # Organize tickets by type
            for ticket in all_tickets:
                issue_type = ticket['fields']['issuetype']['name'].lower()
                key = ticket['key']
                summary = ticket['fields']['summary']
                parent_key = ticket['fields'].get('parent', {}).get('key') if ticket['fields'].get('parent') else None
                
                ticket_info = {
                    "key": key,
                    "summary": summary,
                    "description": ticket['fields'].get('description', ''),
                    "status": ticket['fields']['status']['name'],
                    "parent_key": parent_key,
                    "children": []
                }
                
                if issue_type == 'epic':
                    structure["epics"][key] = ticket_info
                elif issue_type == 'story':
                    structure["stories"][key] = ticket_info
                elif issue_type == 'task':
                    structure["tasks"][key] = ticket_info
                elif issue_type in ['subtask', 'sub-task']:
                    structure["subtasks"][key] = ticket_info
                else:
                    structure["orphaned"].append(ticket_info)
            
            # Build parent-child relationships
            for story_key, story in structure["stories"].items():
                if story["parent_key"] and story["parent_key"] in structure["epics"]:
                    structure["epics"][story["parent_key"]]["children"].append(story_key)
            
            for task_key, task in structure["tasks"].items():
                parent_key = task["parent_key"]
                if parent_key:
                    if parent_key in structure["stories"]:
                        structure["stories"][parent_key]["children"].append(task_key)
                    elif parent_key in structure["epics"]:
                        structure["epics"][parent_key]["children"].append(task_key)
            
            for subtask_key, subtask in structure["subtasks"].items():
                parent_key = subtask["parent_key"]
                if parent_key:
                    if parent_key in structure["stories"]:
                        structure["stories"][parent_key]["children"].append(subtask_key)
                    elif parent_key in structure["tasks"]:
                        structure["tasks"][parent_key]["children"].append(subtask_key)
            
            return structure
            
        except Exception as e:
            logger.error(f"Error getting hierarchical structure: {e}")
            return {"epics": {}, "stories": {}, "tasks": {}, "subtasks": {}, "orphaned": []}

    async def get_project_issue_types(self, project_key: str) -> Dict[str, Dict[str, Any]]:
        """Get available issue types for a project with hierarchy levels and IDs for proper validation"""
        try:
            async with aiohttp.ClientSession() as session:
                # Get project details with issue type hierarchy information
                async with session.get(
                    f"{self.base_url}/project/{project_key}",
                    headers=self.headers
                ) as project_response:
                    if project_response.status != 200:
                        logger.error(f"Failed to get project details: {project_response.status}")
                        return {}
                    
                    project_data = await project_response.json()
                    issue_type_metadata = {}
                    
                    # Extract issue types with their IDs and hierarchy levels
                    for issue_type in project_data.get('issueTypes', []):
                        name = issue_type['name']
                        issue_id = issue_type['id']
                        name_lower = name.lower()
                        
                        # Determine hierarchy level based on issue type characteristics
                        hierarchy_level = self._determine_hierarchy_level(name_lower, issue_type)
                        
                        issue_type_info = {
                            'id': issue_id,
                            'name': name,
                            'hierarchy_level': hierarchy_level,
                            'subtask': issue_type.get('subtask', False)
                        }
                        
                        # Store with normalized keys
                        issue_type_metadata[name_lower] = issue_type_info
                        
                        # Create semantic mappings
                        if 'epic' in name_lower:
                            issue_type_metadata['epic'] = issue_type_info
                        elif 'story' in name_lower or 'storia' in name_lower:
                            issue_type_metadata['story'] = issue_type_info
                        elif (name_lower in ['task', 'attività', 'compito'] and 
                              'sub' not in name_lower and 'sotto' not in name_lower):
                            issue_type_metadata['task'] = issue_type_info
                        elif ('sub' in name_lower or 'sotto' in name_lower or 
                              issue_type.get('subtask', False)):
                            issue_type_metadata['subtask'] = issue_type_info
                            issue_type_metadata['sub-task'] = issue_type_info
                        elif 'bug' in name_lower or 'difetto' in name_lower:
                            issue_type_metadata['bug'] = issue_type_info
                    
                    # Validate hierarchy and provide fallbacks
                    issue_type_metadata = await self._validate_and_fix_hierarchy(
                        issue_type_metadata, project_key
                    )
                    
                    logger.info(f"Found issue types with hierarchy for {project_key}: {
                        {k: f'{v['name']} (Level {v['hierarchy_level']})' 
                         for k, v in issue_type_metadata.items()}
                    }")
                    return issue_type_metadata
                    
        except Exception as e:
            logger.error(f"Error getting project issue types with hierarchy: {e}")
            return {}

    def _determine_hierarchy_level(self, name_lower: str, issue_type: Dict) -> int:
        """Determine hierarchy level for an issue type"""
        # Subtasks are always level 0 (lowest)
        if issue_type.get('subtask', False) or 'sub' in name_lower or 'sotto' in name_lower:
            return 0
        
        # Epic/Initiative are level 3 (highest standard)
        if 'epic' in name_lower or 'initiative' in name_lower:
            return 3
            
        # Story/Feature are typically level 2
        if 'story' in name_lower or 'storia' in name_lower or 'feature' in name_lower:
            return 2
            
        # Task/Bug are typically level 1
        if ('task' in name_lower or 'attività' in name_lower or 
            'bug' in name_lower or 'difetto' in name_lower):
            return 1
            
        # Default to level 1 for unknown types
        return 1

    async def _validate_and_fix_hierarchy(self, issue_types: Dict[str, Dict], project_key: str) -> Dict[str, Dict]:
        """Validate hierarchy levels and fix common configuration issues"""
        try:
            # Check if we have the basic types we need
            if 'epic' not in issue_types and 'story' not in issue_types:
                logger.warning(f"Project {project_key} missing both Epic and Story types")
                return issue_types
            
            # Fix common hierarchy conflicts
            if 'story' in issue_types and 'task' in issue_types:
                story_level = issue_types['story']['hierarchy_level']
                task_level = issue_types['task']['hierarchy_level']
                
                # If Story and Task are at same level, adjust Task to be one level below
                if story_level == task_level:
                    logger.info(f"Adjusting Task hierarchy level from {task_level} to {task_level-1} to fix parent relationship")
                    issue_types['task']['hierarchy_level'] = task_level - 1
            
            # Ensure Subtasks are always at the bottom
            if 'subtask' in issue_types:
                min_level = min(it['hierarchy_level'] for it in issue_types.values() 
                              if not it.get('subtask', False))
                issue_types['subtask']['hierarchy_level'] = min_level - 1
                if 'sub-task' in issue_types:
                    issue_types['sub-task']['hierarchy_level'] = min_level - 1
            
            return issue_types
            
        except Exception as e:
            logger.error(f"Error validating hierarchy: {e}")
            return issue_types

    async def _validate_parent_hierarchy(self, project_key: str, parent_key: str, 
                                       child_level: int, issue_type_metadata: Dict) -> bool:
        """Validate that parent-child relationship respects Jira hierarchy constraints"""
        try:
            # Get parent issue details
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/issue/{parent_key}",
                    headers=self.headers
                ) as response:
                    if response.status != 200:
                        logger.error(f"Cannot fetch parent issue {parent_key}: {response.status}")
                        return False
                    
                    parent_data = await response.json()
                    parent_issue_type = parent_data['fields']['issuetype']['name']
                    
                    # Find parent's hierarchy level
                    parent_info = None
                    for type_info in issue_type_metadata.values():
                        if type_info['name'] == parent_issue_type:
                            parent_info = type_info
                            break
                    
                    if not parent_info:
                        logger.error(f"Parent issue type '{parent_issue_type}' not found in metadata")
                        return False
                    
                    parent_level = parent_info['hierarchy_level']
                    
                    # Validate hierarchy constraint: parent must be exactly one level above child
                    level_difference = parent_level - child_level
                    
                    if level_difference == 1:
                        logger.info(f"✅ Valid hierarchy: Parent {parent_issue_type} (L{parent_level}) -> Child (L{child_level})")
                        return True
                    else:
                        logger.error(f"❌ Invalid hierarchy: Parent {parent_issue_type} (L{parent_level}) -> Child (L{child_level})")
                        logger.error(f"   Required level difference: 1, Actual: {level_difference}")
                        
                        # Provide helpful guidance
                        if level_difference == 0:
                            logger.error(f"   ⚠️  Parent and child are at same level - use issue links instead of parent field")
                        elif level_difference > 1:
                            logger.error(f"   ⚠️  Hierarchy gap too large - need intermediate issue types")
                        else:
                            logger.error(f"   ⚠️  Parent level is lower than child - reverse relationship needed")
                        
                        return False
                    
        except Exception as e:
            logger.error(f"Error validating parent hierarchy: {e}")
            return False

    async def _find_hierarchical_parent(self, proposal: Dict, parent_summary: str, 
                                      hierarchical_structure: Dict[str, Any]) -> Optional[str]:
        """Find parent based on correct Jira hierarchy rules"""
        issue_type = proposal['issue_type'].lower()
        parent_summary_clean = parent_summary.lower().strip()
        
        if issue_type == 'story':
            # Stories can only have Epic parents
            for epic_key, epic_info in hierarchical_structure["epics"].items():
                if epic_info["summary"].lower().strip() == parent_summary_clean:
                    logger.info(f"✅ Found Epic parent for Story: {epic_key}")
                    return epic_key
                    
        elif issue_type == 'task':
            # Tasks can only have Story parents (NOT Epic!)
            for story_key, story_info in hierarchical_structure["stories"].items():
                if story_info["summary"].lower().strip() == parent_summary_clean:
                    logger.info(f"✅ Found Story parent for Task: {story_key}")
                    return story_key
                    
        elif issue_type in ['subtask', 'sub-task', 'sottotask']:
            # Subtasks can only have Task parents (NOT Story/Epic!)
            for task_key, task_info in hierarchical_structure["tasks"].items():
                if task_info["summary"].lower().strip() == parent_summary_clean:
                    logger.info(f"✅ Found Task parent for Subtask: {task_key}")
                    return task_key
        
        logger.warning(f"❌ No valid parent found for {issue_type}: '{parent_summary}'")
        return None

    async def find_matching_epic(self, epic_summary: str, structure: Dict[str, Any]) -> Optional[str]:
        """Find an existing Epic that matches the given summary"""
        epic_summary_lower = epic_summary.lower().strip()
        
        for epic_key, epic_info in structure["epics"].items():
            existing_summary_lower = epic_info["summary"].lower().strip()
            
            # Exact match
            if epic_summary_lower == existing_summary_lower:
                return epic_key
            
            # Check if they contain similar keywords (at least 70% similarity)
            epic_words = set(epic_summary_lower.split())
            existing_words = set(existing_summary_lower.split())
            
            if len(epic_words) > 0 and len(existing_words) > 0:
                intersection = epic_words.intersection(existing_words)
                similarity = len(intersection) / max(len(epic_words), len(existing_words))
                
                if similarity >= 0.7:
                    return epic_key
        
        return None

    async def find_matching_story(self, story_summary: str, epic_key: str, structure: Dict[str, Any]) -> Optional[str]:
        """Find an existing Story under a specific Epic that matches the given summary"""
        story_summary_lower = story_summary.lower().strip()
        
        # Get stories under this epic
        epic_children = structure["epics"].get(epic_key, {}).get("children", [])
        
        for story_key in epic_children:
            if story_key in structure["stories"]:
                story_info = structure["stories"][story_key]
                existing_summary_lower = story_info["summary"].lower().strip()
                
                # Exact match
                if story_summary_lower == existing_summary_lower:
                    return story_key
                
                # Check similarity (at least 70%)
                story_words = set(story_summary_lower.split())
                existing_words = set(existing_summary_lower.split())
                
                if len(story_words) > 0 and len(existing_words) > 0:
                    intersection = story_words.intersection(existing_words)
                    similarity = len(intersection) / max(len(story_words), len(existing_words))
                    
                    if similarity >= 0.7:
                        return story_key
        
        return None

    async def create_ticket(self, project_key: str, issue_type: str, summary: str, description: str, 
                           parent_key: Optional[str] = None, story_points: Optional[int] = None, 
                           priority: Optional[str] = None) -> Optional[str]:
        """Create a new Jira ticket with hierarchical validation and proper parent relationships"""
        try:
            # Get issue type metadata with hierarchy information
            issue_type_metadata = await self.get_project_issue_types(project_key)
            
            # Get issue type info
            issue_type_info = issue_type_metadata.get(issue_type.lower())
            if not issue_type_info:
                logger.error(f"Issue type '{issue_type}' not found in project {project_key}")
                return None
            
            mapped_issue_type = issue_type_info['name']
            current_hierarchy_level = issue_type_info['hierarchy_level']
            
            logger.info(f"Creating {issue_type} (level {current_hierarchy_level}): {summary}")
            
            # Validate parent relationship if specified
            if parent_key:
                parent_valid = await self._validate_parent_hierarchy(
                    project_key, parent_key, current_hierarchy_level, issue_type_metadata
                )
                if not parent_valid:
                    logger.error(f"❌ HIERARCHY VIOLATION: Cannot create {issue_type} as child of {parent_key}")
                    logger.error(f"   {issue_type} (level {current_hierarchy_level}) requires parent at level {current_hierarchy_level + 1}")
                    return None
                
                logger.info(f"✅ Hierarchy validation passed for {issue_type} -> parent {parent_key}")
            # Build description object
            description_obj = {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": description
                            }
                        ]
                    }
                ]
            }

            # Use issue type ID instead of name for more stable API calls
            payload = {
                "fields": {
                    "project": {"key": project_key},
                    "summary": summary,
                    "description": description_obj,
                    "issuetype": {"id": issue_type_info['id']}  # Use stable ID instead of name
                }
            }

            # Add parent relationship for hierarchical structure
            # Use parent field for all child relationships (Epic->Story, Story->Subtask)
            if parent_key:
                if (issue_type.lower() in ['story', 'task'] or 
                    issue_type.lower() in ['subtask', 'sub-task'] or
                    'sub' in mapped_issue_type.lower() or 'sotto' in mapped_issue_type.lower()):
                    payload["fields"]["parent"] = {"key": parent_key}
                    logger.info(f"Setting parent {parent_key} for {issue_type} {summary}")

            # Add story points if provided (usually customfield_10016)
            if story_points and issue_type.lower() in ['story', 'task', 'subtask', 'sub-task']:
                payload["fields"]["customfield_10016"] = story_points

            # Add priority if provided
            if priority:
                priority_mapping = {
                    "high": "High",
                    "medium": "Medium", 
                    "low": "Low",
                    "highest": "Highest",
                    "lowest": "Lowest"
                }
                priority_name = priority_mapping.get(priority.lower(), priority)
                payload["fields"]["priority"] = {"name": priority_name}

            logger.info(f"Creating {issue_type} ticket: {summary} (parent: {parent_key})")
            logger.debug(f"Payload: {json.dumps(payload, indent=2)}")

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/issue",
                    headers=self.headers,
                    json=payload
                ) as response:
                    if response.status in [200, 201]:
                        data = await response.json()
                        ticket_key = data.get('key')
                        logger.info(f"Successfully created ticket: {ticket_key}")
                        return ticket_key
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to create ticket: {response.status} - {error_text}")
                        return None
        except Exception as e:
            logger.error(f"Error creating ticket: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    async def link_to_parent(self, child_key: str, parent_key: str, link_type: str = "epic") -> bool:
        """Link a child issue to its parent using appropriate Jira mechanism"""
        try:
            if link_type == "epic":
                # Try Epic Link field first (most common for Story -> Epic)
                await self._try_epic_link_field(child_key, parent_key)
                
            # Try issue link as fallback
            success = await self._try_issue_link(child_key, parent_key, link_type)
            
            if success:
                logger.info(f"Successfully linked {child_key} to {link_type} {parent_key}")
                return True
            else:
                logger.warning(f"Could not link {child_key} to {parent_key}, but continuing...")
                return True  # Don't fail the creation process
                
        except Exception as e:
            logger.error(f"Error linking {child_key} to {parent_key}: {e}")
            return True  # Don't fail the creation for this

    async def _try_epic_link_field(self, story_key: str, epic_key: str) -> bool:
        """Try to link using Epic Link field (customfield_10014 or similar)"""
        try:
            # Common Epic Link field names
            epic_link_fields = ["customfield_10014", "customfield_10008", "customfield_10002"]
            
            for field_id in epic_link_fields:
                payload = {
                    "fields": {
                        field_id: epic_key
                    }
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.put(
                        f"{self.base_url}/issue/{story_key}",
                        headers=self.headers,
                        json=payload
                    ) as response:
                        if response.status in [200, 204]:
                            logger.info(f"Successfully set Epic Link using {field_id}")
                            return True
                        else:
                            logger.debug(f"Epic Link field {field_id} not available")
                            
            return False
        except Exception as e:
            logger.debug(f"Epic Link field update failed: {e}")
            return False

    async def _try_issue_link(self, child_key: str, parent_key: str, link_type: str) -> bool:
        """Try to create an issue link between child and parent"""
        try:
            # Different link type names to try
            link_types_to_try = [
                "Epic-Story Link",
                "Relates", 
                "Blocks",
                "Child-Parent",
                "Hierarchy"
            ]
            
            for link_name in link_types_to_try:
                payload = {
                    "type": {
                        "name": link_name
                    },
                    "inwardIssue": {
                        "key": child_key
                    },
                    "outwardIssue": {
                        "key": parent_key
                    }
                }

                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.base_url}/issueLink",
                        headers=self.headers,
                        json=payload
                    ) as response:
                        if response.status in [200, 201]:
                            logger.info(f"Successfully created {link_name} link")
                            return True
                        else:
                            logger.debug(f"Link type {link_name} not available")
            
            return False
        except Exception as e:
            logger.debug(f"Issue link creation failed: {e}")
            return False

    async def update_ticket(self, ticket_key: str, summary: Optional[str] = None, description: Optional[str] = None) -> bool:
        """Update an existing Jira ticket"""
        try:
            fields = {}
            if summary:
                fields["summary"] = summary
            if description:
                fields["description"] = {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": description
                                }
                            ]
                        }
                    ]
                }

            payload = {"fields": fields}

            async with aiohttp.ClientSession() as session:
                async with session.put(
                    f"{self.base_url}/issue/{ticket_key}",
                    headers=self.headers,
                    json=payload
                ) as response:
                    return response.status in [200, 204]
        except Exception as e:
            logger.error(f"Error updating ticket: {e}")
            return False

    async def get_projects(self) -> List[Dict[str, Any]]:
        """Get all accessible Jira projects"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/project",
                    headers=self.headers
                ) as response:
                    if response.status == 200:
                        projects = await response.json()
                        return [
                            {
                                "key": project["key"],
                                "name": project["name"],
                                "id": project["id"]
                            }
                            for project in projects
                        ]
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to fetch projects: {response.status} - {error_text}")
                        return []
        except Exception as e:
            logger.error(f"Error fetching projects: {e}")
            return []

# ==================== LLM Analysis Service ====================

async def analyze_meeting_with_llm(meeting_minutes: str, project_key: str, hierarchical_structure: Dict[str, Any]) -> List[ProposedTicket]:
    """Use OpenRouter (GPT-4o) to analyze meeting minutes and propose Jira changes with hierarchical awareness"""
    try:
        # Format existing hierarchical structure for the LLM
        structure_summary = "EXISTING PROJECT STRUCTURE:\n\n"
        
        # Format Epics and their children
        if hierarchical_structure["epics"]:
            structure_summary += "📋 EPICS:\n"
            for epic_key, epic_info in hierarchical_structure["epics"].items():
                structure_summary += f"  • {epic_key}: {epic_info['summary']}\n"
                
                # Show Stories under this Epic
                epic_stories = [child for child in epic_info['children'] if child in hierarchical_structure["stories"]]
                if epic_stories:
                    structure_summary += "    📖 Stories:\n"
                    for story_key in epic_stories:
                        story = hierarchical_structure["stories"][story_key]
                        structure_summary += f"      - {story_key}: {story['summary']}\n"
                        
                        # Show Tasks/Subtasks under this Story
                        story_children = [child for child in story['children'] 
                                        if child in hierarchical_structure["tasks"] or child in hierarchical_structure["subtasks"]]
                        if story_children:
                            for child_key in story_children:
                                if child_key in hierarchical_structure["tasks"]:
                                    task = hierarchical_structure["tasks"][child_key]
                                    structure_summary += f"        ⚙️  {child_key}: {task['summary']}\n"
                                elif child_key in hierarchical_structure["subtasks"]:
                                    subtask = hierarchical_structure["subtasks"][child_key]
                                    structure_summary += f"        🔧 {child_key}: {subtask['summary']}\n"
                structure_summary += "\n"
        
        # Show orphaned Stories (not under any Epic)
        orphaned_stories = [key for key, story in hierarchical_structure["stories"].items() 
                          if not story.get("parent_key")]
        if orphaned_stories:
            structure_summary += "📖 INDEPENDENT STORIES:\n"
            for story_key in orphaned_stories:
                story = hierarchical_structure["stories"][story_key]
                structure_summary += f"  • {story_key}: {story['summary']}\n"
            structure_summary += "\n"

        # Show orphaned Tasks
        orphaned_tasks = [key for key, task in hierarchical_structure["tasks"].items() 
                         if not task.get("parent_key")]
        if orphaned_tasks:
            structure_summary += "⚙️  INDEPENDENT TASKS:\n"
            for task_key in orphaned_tasks:
                task = hierarchical_structure["tasks"][task_key]
                structure_summary += f"  • {task_key}: {task['summary']}\n"
            structure_summary += "\n"

        system_message = """You are a senior Jira project management assistant specializing in structured task decomposition with STRICT hierarchical awareness.

🚨 CRITICAL HIERARCHY RULES:
1. **ALWAYS check existing Epics first** - If a similar Epic exists, use it instead of creating a new one
2. **ALWAYS check existing Stories under Epics** - Reuse existing Stories when appropriate
3. **Epic → Story → Task/Subtask** hierarchy is MANDATORY
4. **Never create orphaned issues** - Every Story must belong to an Epic, every Task/Subtask to a Story

📋 ISSUE HIERARCHY (MANDATORY STRUCTURE):
- **Epic**: Major business initiatives (spans multiple sprints) - High-level business goals
- **Story**: Important user-facing features or major technical components - Each Story is a significant deliverable
- **Task**: Technical implementation work under Stories - Specific development work (APIs, components, etc.)  
- **Subtask**: Detailed implementation steps under Tasks - Granular, actionable work items
- **Bug**: Defects to be fixed

🚫 FORBIDDEN PARENT RELATIONSHIPS (JIRA API VALIDATION WILL REJECT):
- Task parent_summary → Epic title (FORBIDDEN: Tasks cannot be direct children of Epics in Jira!)
- Subtask parent_summary → Story title (FORBIDDEN: Subtasks cannot be direct children of Stories in Jira!)
- Subtask parent_summary → Epic title (FORBIDDEN: Subtasks cannot skip hierarchy levels!)

✅ ONLY VALID JIRA HIERARCHY (API-COMPLIANT):
- Story parent_summary → Epic title (Stories are children of Epics)
- Task parent_summary → Story title (Tasks are children of Stories ONLY)
- Subtask parent_summary → Task title (Subtasks are children of Tasks ONLY)

🚨 JIRA API HIERARCHY ENFORCEMENT (MANDATORY FOR API SUCCESS):
1. **Epic → Story ONLY**: Stories can only have Epic parents (via parent field)
2. **Story → Task ONLY**: Tasks can only have Story parents (NOT Epic parents!)
3. **Task → Subtask ONLY**: Subtasks can only have Task parents (NOT Story/Epic parents!)
4. **NO HIERARCHY SKIPPING**: Every level must be present - no Task→Epic or Subtask→Story links
5. **SEQUENTIAL CREATION**: Parent must exist before creating children (API dependency)

🎯 JIRA API-COMPLIANT HIERARCHY (STRICT ENFORCEMENT):

LEVEL 1: Epic (1 per meeting)
├── LEVEL 2: Story (parent_summary = Epic title)
    ├── LEVEL 3: Task (parent_summary = Story title - NOT Epic!)
        ├── LEVEL 4: Subtask (parent_summary = Task title - NOT Story!)

**Stories** (User-Facing Features) - MUST HAVE MULTIPLE TASKS:
- **Business Value**: Clear user benefit, feature description, acceptance criteria
- **Feature Scope**: Complete deliverable functionality (login system, dashboard, API)
- **Task Breakdown**: MUST decompose into 3-5 technical Tasks
- **Story Points**: 8-13 (reflecting multiple Tasks underneath)

**Tasks** (Technical Components) - MUST HAVE MULTIPLE SUBTASKS:
- **Technical Work**: Specific development area (backend API, React component, database schema)
- **Implementation Strategy**: Technology stack, architecture approach, integration points
- **Subtask Breakdown**: MUST decompose into 3-4 granular Subtasks
- **Story Points**: 3-5 (reflecting multiple Subtasks underneath)

**Subtasks** (Implementation Details):
- **Granular Actions**: Specific coding steps, configurations, or setups
- **Clear Acceptance Criteria**: Exactly what needs to be coded/configured
- **Dependency Awareness**: What must be done before this step
- **Actionable Size**: 2-8 hours of focused development work

📝 MANDATORY BREAKDOWN EXAMPLE:
Meeting requirement: "Add user authentication"
Create this COMPLETE HIERARCHY:

1. **Epic**: "User Management System" (parent_summary: null)

2. **Story**: "User Registration and Login System" (parent_summary: "User Management System")
   - **Task**: "Backend Authentication API Development" (parent_summary: "User Registration and Login System") ⚠️ CORRECT: Task → Story
     - **Subtask**: "Create user registration endpoint with email validation" (parent_summary: "Backend Authentication API Development") ⚠️ CORRECT: Subtask → Task
     - **Subtask**: "Implement login endpoint with JWT token generation" (parent_summary: "Backend Authentication API Development")
     - **Subtask**: "Add password hashing with bcrypt" (parent_summary: "Backend Authentication API Development")
   - **Task**: "Frontend Authentication Components" (parent_summary: "User Registration and Login System") ⚠️ CORRECT: Task → Story
     - **Subtask**: "Create login form component with validation" (parent_summary: "Frontend Authentication Components") ⚠️ CORRECT: Subtask → Task
     - **Subtask**: "Create registration form with field validation" (parent_summary: "Frontend Authentication Components")
     - **Subtask**: "Implement authentication context and routing guards" (parent_summary: "Frontend Authentication Components")
   - **Task**: "Database Schema and Security" (parent_summary: "User Registration and Login System") ⚠️ CORRECT: Task → Story
     - **Subtask**: "Create users table with proper indexes" (parent_summary: "Database Schema and Security") ⚠️ CORRECT: Subtask → Task
     - **Subtask**: "Implement rate limiting for login attempts" (parent_summary: "Database Schema and Security")

3. **Story**: "Password Recovery System" (parent_summary: "User Management System")
   - **Task**: "Email-based Password Reset" (parent_summary: "Password Recovery System") ⚠️ CORRECT: Task → Story (NOT → Epic)
   - **Task**: "Security Token Management" (parent_summary: "Password Recovery System") ⚠️ CORRECT: Task → Story (NOT → Epic)

🌳 MANDATORY HIERARCHY RULES:
- Every **Story** MUST have an **Epic** as parent (parent_summary = Epic title)
- Every **Task** MUST have a **Story** as parent (parent_summary = Story title - NEVER Epic title!)  
- Every **Subtask** MUST have a **Task** as parent (parent_summary = Task title - NEVER Story/Epic title!)
- **NEVER create orphaned Stories** - each Story must represent a complete feature with multiple Tasks
- **ALWAYS create Tasks under Stories** - minimum 2-5 Tasks per Story
- **DECOMPOSE Tasks into Subtasks** - detailed implementation steps
- NO single-task Stories allowed - if a Story has only one Task, merge them or add more Tasks

⛔ FORBIDDEN EXAMPLES:
- Task with parent_summary="Epic Name" (WRONG - Tasks belong to Stories, not Epics!)
- Subtask with parent_summary="Story Name" (WRONG - Subtasks belong to Tasks, not Stories!)

🔧 DECOMPOSITION PATTERNS:

**Frontend Story** → Tasks:
- "UI Component Development" → Subtasks: Create component, Add styling, Add interactions, Add tests
- "State Management Integration" → Subtasks: Setup store, Create actions, Add reducers, Connect components
- "API Integration" → Subtasks: Create service layer, Add error handling, Implement loading states

**Backend Story** → Tasks:  
- "API Endpoint Development" → Subtasks: Create controller, Add validation, Implement business logic, Add tests
- "Database Schema Changes" → Subtasks: Create migration, Update models, Add indexes, Test queries
- "Authentication Integration" → Subtasks: Add middleware, Create JWT utils, Add role checks

**Full-Stack Story** → Tasks:
- "Backend API" → Multiple subtasks for endpoints, validation, business logic
- "Frontend Integration" → Multiple subtasks for components, services, error handling
- "Database Changes" → Multiple subtasks for schema, migrations, optimizations
- "Testing & Documentation" → Multiple subtasks for unit tests, integration tests, API docs

📊 REQUIREMENTS:
- Include story points (1,2,3,5,8,13) based on complexity and effort
- Set priority (High, Medium, Low) based on business impact
- Use "parent_summary" to specify exact parent Epic/Story title
- Provide detailed reasoning for each change

You must respond ONLY with a valid JSON array. Each item must have this exact structure:
{
  "action": "create" or "modify" or "reuse_existing",
  "ticket_key": "PROJ-123" (for modify/reuse_existing actions),
  "issue_type": "Epic" or "Story" or "Task" or "Subtask" or "Bug",
  "summary": "Clear, actionable title - Stories: feature-focused, Tasks: technical-focused, Subtasks: implementation-focused",
  "description": "Detailed description with:\n- For Stories: User value, business impact, feature scope\n- For Tasks: Technical approach, implementation strategy, tools/frameworks\n- For Subtasks: Specific coding steps, acceptance criteria, dependencies",
  "story_points": 1-13 (Stories: 5-13, Tasks: 2-8, Subtasks: 1-3),
  "priority": "High" or "Medium" or "Low",
  "parent_summary": "EXACT title of parent (Stories→Epic, Tasks→Story, Subtasks→Task)",
  "dependencies": ["Summary of dependent issues"] (optional),
  "reasoning": "Why this specific task is needed and how it contributes to the Epic/Story goal",
  "current_summary": "existing summary" (only for modify actions),
  "current_description": "existing description" (only for modify actions)
}

🚨 IMPORTANT: 
- NEVER create duplicate Epics or Stories
- ALWAYS specify parent_summary for proper hierarchy
- Use action "reuse_existing" if an issue already covers the requirement
- Make tasks SPECIFIC and ACTIONABLE with clear technical details
- Respond with ONLY a JSON array, no additional text"""

        user_prompt = f"""Project: {project_key}

{structure_summary}

Meeting Minutes:
{meeting_minutes}

📝 TASK: Analyze the meeting minutes and propose hierarchical Jira changes. 
🎯 PRIORITY: Reuse existing Epics/Stories when possible, create new issues only when necessary.
📋 FORMAT: Respond with JSON array following the exact structure specified."""

        # Initialize AI client (OpenAI or OpenRouter)
        openai_api_key = os.environ.get('OPENAI_API_KEY')
        openrouter_api_key = os.environ.get('OPENROUTER_API_KEY')
        
        if openrouter_api_key:
            client = AsyncOpenAI(
                api_key=openrouter_api_key,
                base_url="https://openrouter.ai/api/v1"
            )
            model_name = os.environ.get('OPENROUTER_MODEL', 'openai/gpt-4o')
            logger.info(f"Using OpenRouter with model: {model_name}")
        elif openai_api_key:
            client = AsyncOpenAI(api_key=openai_api_key)
            model_name = os.environ.get('OPENAI_MODEL', 'gpt-4o')
            logger.info(f"Using OpenAI with model: {model_name}")
        else:
            raise ValueError("Neither OPENAI_API_KEY nor OPENROUTER_API_KEY is set in environment variables")

        # Send message to OpenRouter
        response = await client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=4000
        )

        response_text = response.choices[0].message.content
        logger.info(f"OpenRouter Response: {response_text[:500]}...")

        # Parse response
        # Remove markdown code blocks if present
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            response_text = "\n".join(lines[1:-1]) if len(lines) > 2 else response_text
            response_text = response_text.replace("```json", "").replace("```", "")

        # Clean up the response text to remove invalid control characters
        import re
        response_text = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', response_text.strip())
        
        # Try to extract JSON if it's embedded in other text
        json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if json_match:
            response_text = json_match.group()

        proposals_data = json.loads(response_text.strip())

        # Convert to ProposedTicket objects
        proposals = [ProposedTicket(**item) for item in proposals_data]

        logger.info(f"Generated {len(proposals)} proposals")
        return proposals

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON: {e}")
        logger.error(f"Response was: {response_text if 'response_text' in locals() else 'No response'}")
        return []
    except Exception as e:
        logger.error(f"Error in OpenRouter API call: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []

# ==================== API Routes ====================

@api_router.get("/")
async def root():
    return {"message": "Jira Meeting Sync API", "status": "running"}

# Jira Configuration endpoints
@api_router.post("/jira/config")
async def save_jira_config(config: JiraConfigCreate):
    """Save Jira configuration"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Delete existing config (single-user setup)
            await db.execute('DELETE FROM jira_configs')

            config_obj = JiraConfig(**config.model_dump())

            await db.execute(
                'INSERT INTO jira_configs (id, jira_domain, jira_email, jira_api_token, created_at) VALUES (?, ?, ?, ?, ?)',
                (config_obj.id, config_obj.jira_domain, config_obj.jira_email,
                 config_obj.jira_api_token, config_obj.created_at.isoformat())
            )
            await db.commit()

        return {"success": True, "message": "Jira configuration saved successfully"}
    except Exception as e:
        logger.error(f"Error saving Jira config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/jira/config")
async def get_jira_config():
    """Get saved Jira configuration (without API token for security)"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM jira_configs LIMIT 1') as cursor:
                row = await cursor.fetchone()

                if not row:
                    return {"configured": False}

                # Don't return the API token
                return {
                    "configured": True,
                    "jira_domain": row['jira_domain'],
                    "jira_email": row['jira_email']
                }
    except Exception as e:
        logger.error(f"Error fetching Jira config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/jira/test-connection", response_model=JiraConnectionTest)
async def test_jira_connection():
    """Test connection to Jira"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM jira_configs LIMIT 1') as cursor:
                row = await cursor.fetchone()

                if not row:
                    return JiraConnectionTest(
                        success=False,
                        message="No Jira configuration found. Please configure Jira first."
                    )

                jira_client = JiraAPIClient(
                    domain=row['jira_domain'],
                    email=row['jira_email'],
                    api_token=row['jira_api_token']
                )

                success = await jira_client.test_connection()

                return JiraConnectionTest(
                    success=success,
                    message="Successfully connected to Jira!" if success else "Failed to connect to Jira. Please check your credentials."
                )
    except Exception as e:
        logger.error(f"Error testing Jira connection: {e}")
        return JiraConnectionTest(
            success=False,
            message=f"Error: {str(e)}"
        )

@api_router.post("/jira/test-credentials", response_model=JiraConnectionTest)
async def test_jira_credentials(config: JiraConfigTestRequest):
    """Test Jira credentials without saving them"""
    try:
        jira_client = JiraAPIClient(
            domain=config.jira_domain,
            email=config.jira_email,
            api_token=config.jira_api_token
        )

        success = await jira_client.test_connection()

        return JiraConnectionTest(
            success=success,
            message="Successfully connected to Jira!" if success else "Failed to connect to Jira. Please check your credentials."
        )
    except Exception as e:
        logger.error(f"Error testing Jira credentials: {e}")
        return JiraConnectionTest(
            success=False,
            message=f"Error: {str(e)}"
        )

@api_router.get("/jira/projects")
async def get_jira_projects():
    """Get all accessible Jira projects"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM jira_configs LIMIT 1') as cursor:
                row = await cursor.fetchone()

                if not row:
                    raise HTTPException(status_code=400, detail="No Jira configuration found. Please configure Jira first.")

                jira_client = JiraAPIClient(
                    domain=row['jira_domain'],
                    email=row['jira_email'],
                    api_token=row['jira_api_token']
                )

                projects = await jira_client.get_projects()
                return {"projects": projects}
    except Exception as e:
        logger.error(f"Error fetching Jira projects: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/jira/projects/{project_key}/structure")
async def get_project_structure(project_key: str):
    """Get hierarchical structure of a specific project"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM jira_configs LIMIT 1') as cursor:
                row = await cursor.fetchone()

                if not row:
                    raise HTTPException(status_code=400, detail="No Jira configuration found. Please configure Jira first.")

                jira_client = JiraAPIClient(
                    domain=row['jira_domain'],
                    email=row['jira_email'],
                    api_token=row['jira_api_token']
                )

                structure = await jira_client.get_hierarchical_structure(project_key)
                return {
                    "project_key": project_key,
                    "structure": structure,
                    "summary": {
                        "epics_count": len(structure["epics"]),
                        "stories_count": len(structure["stories"]),
                        "tasks_count": len(structure["tasks"]),
                        "subtasks_count": len(structure["subtasks"]),
                        "orphaned_count": len(structure["orphaned"])
                    }
                }
    except Exception as e:
        logger.error(f"Error fetching project structure: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/jira/projects/{project_key}/issue-types")
async def get_project_issue_types(project_key: str):
    """Get available issue types for a project"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM jira_configs LIMIT 1') as cursor:
                row = await cursor.fetchone()

                if not row:
                    raise HTTPException(status_code=400, detail="No Jira configuration found. Please configure Jira first.")

                jira_client = JiraAPIClient(
                    domain=row['jira_domain'],
                    email=row['jira_email'],
                    api_token=row['jira_api_token']
                )

                issue_types = await jira_client.get_project_issue_types(project_key)
                return {"issue_types": issue_types}
    except Exception as e:
        logger.error(f"Error fetching project issue types: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@api_router.get("/analysis/client-names")
async def get_client_names():
    """Get all unique client names from previous analyses"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute('SELECT DISTINCT client_name FROM meeting_analyses WHERE client_name IS NOT NULL ORDER BY client_name') as cursor:
                rows = await cursor.fetchall()
                client_names = [row[0] for row in rows if row[0].strip()]
                return {"client_names": client_names}
    except Exception as e:
        logger.error(f"Error fetching client names: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/analysis/project-names")
async def get_project_names():
    """Get all unique project names from previous analyses"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute('SELECT DISTINCT project_name FROM meeting_analyses WHERE project_name IS NOT NULL ORDER BY project_name') as cursor:
                rows = await cursor.fetchall()
                project_names = [row[0] for row in rows if row[0].strip()]
                return {"project_names": project_names}
    except Exception as e:
        logger.error(f"Error fetching project names: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Meeting Analysis endpoints
@api_router.post("/analysis/create")
async def create_analysis(analysis_request: MeetingAnalysisCreate):
    """Create a new meeting analysis"""
    try:
        # Get Jira config
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM jira_configs LIMIT 1') as cursor:
                config_row = await cursor.fetchone()

                if not config_row:
                    raise HTTPException(status_code=400, detail="Jira not configured")

        # Initialize Jira client
        jira_client = JiraAPIClient(
            domain=config_row['jira_domain'],
            email=config_row['jira_email'],
            api_token=config_row['jira_api_token']
        )

        # Fetch existing hierarchical structure
        logger.info(f"Fetching hierarchical structure for project: {analysis_request.jira_project_key}")
        hierarchical_structure = await jira_client.get_hierarchical_structure(analysis_request.jira_project_key)
        logger.info(f"Found project structure: {len(hierarchical_structure['epics'])} epics, {len(hierarchical_structure['stories'])} stories, {len(hierarchical_structure['tasks'])} tasks")
        
        # If we couldn't fetch existing structure, create an empty one to continue
        if not hierarchical_structure or all(len(v) == 0 for k, v in hierarchical_structure.items() if k != 'orphaned'):
            logger.warning("No existing tickets found or failed to fetch - proceeding with empty structure")
            hierarchical_structure = {"epics": {}, "stories": {}, "tasks": {}, "subtasks": {}, "orphaned": []}

        # Analyze with LLM using hierarchical structure
        proposals = await analyze_meeting_with_llm(
            meeting_minutes=analysis_request.meeting_minutes,
            project_key=analysis_request.jira_project_key,
            hierarchical_structure=hierarchical_structure
        )

        # Create analysis record
        analysis = MeetingAnalysis(
            **analysis_request.model_dump(),
            proposed_changes=proposals
        )

        # Save to database
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                '''INSERT INTO meeting_analyses
                   (id, jira_project_key, client_name, project_name, meeting_minutes,
                    proposed_changes, status, created_at, processed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (analysis.id, analysis.jira_project_key, analysis.client_name,
                 analysis.project_name, analysis.meeting_minutes,
                 json.dumps([p.model_dump() for p in analysis.proposed_changes]),
                 analysis.status, analysis.created_at.isoformat(), None)
            )
            await db.commit()

        return {"success": True, "analysis_id": analysis.id, "proposals_count": len(proposals)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating analysis: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/analysis/{analysis_id}")
async def get_analysis(analysis_id: str):
    """Get analysis by ID"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM meeting_analyses WHERE id = ?', (analysis_id,)) as cursor:
                row = await cursor.fetchone()

                if not row:
                    raise HTTPException(status_code=404, detail="Analysis not found")

                return {
                    "id": row['id'],
                    "jira_project_key": row['jira_project_key'],
                    "client_name": row['client_name'],
                    "project_name": row['project_name'],
                    "meeting_minutes": row['meeting_minutes'],
                    "proposed_changes": json.loads(row['proposed_changes']),
                    "status": row['status'],
                    "created_at": row['created_at'],
                    "processed_at": row['processed_at']
                }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/analysis")
async def get_all_analyses():
    """Get all analyses"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM meeting_analyses ORDER BY created_at DESC LIMIT 100') as cursor:
                rows = await cursor.fetchall()

                analyses = []
                for row in rows:
                    analyses.append({
                        "id": row['id'],
                        "jira_project_key": row['jira_project_key'],
                        "client_name": row['client_name'],
                        "project_name": row['project_name'],
                        "meeting_minutes": row['meeting_minutes'],
                        "proposed_changes": json.loads(row['proposed_changes']),
                        "status": row['status'],
                        "created_at": row['created_at'],
                        "processed_at": row['processed_at']
                    })

                return {"analyses": analyses}
    except Exception as e:
        logger.error(f"Error fetching analyses: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/analysis/{analysis_id}/approve")
async def approve_proposals(analysis_id: str, approval: ApprovalRequest):
    """Approve and execute proposals"""
    try:
        # Get analysis
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM meeting_analyses WHERE id = ?', (analysis_id,)) as cursor:
                row = await cursor.fetchone()

                if not row:
                    raise HTTPException(status_code=404, detail="Analysis not found")

                proposed_changes = json.loads(row['proposed_changes'])
                jira_project_key = row['jira_project_key']

        # Get Jira config
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM jira_configs LIMIT 1') as cursor:
                config_row = await cursor.fetchone()

                if not config_row:
                    raise HTTPException(status_code=400, detail="Jira not configured")

        jira_client = JiraAPIClient(
            domain=config_row['jira_domain'],
            email=config_row['jira_email'],
            api_token=config_row['jira_api_token']
        )

        # Get current hierarchical structure for parent resolution
        hierarchical_structure = await jira_client.get_hierarchical_structure(jira_project_key)
        
        results = []
        created_tickets = {}  # Track newly created tickets by their summary
        failed_parents = set()  # Track failed parent creations to prevent cascade failures

        # Sort proposals by hierarchy: Epics first, then Stories, then Tasks/Subtasks
        hierarchy_order = {"Epic": 1, "Story": 2, "Task": 3, "Subtask": 4, "Sub-task": 4, "Bug": 5}
        approved_proposals = [(idx, proposed_changes[idx]) for idx in approval.approved_indices if idx < len(proposed_changes)]
        approved_proposals.sort(key=lambda x: hierarchy_order.get(x[1].get('issue_type', 'Bug'), 6))

        # JIRA API HIERARCHY PRE-VALIDATION
        validation_errors = []
        for idx, proposal in approved_proposals:
            issue_type = proposal.get('issue_type', '').lower()
            parent_summary = proposal.get('parent_summary')
            
            if proposal.get('action') == 'create':
                # Story without Epic parent
                if issue_type == 'story' and not parent_summary:
                    validation_errors.append(f"Story '{proposal.get('summary')}' missing Epic parent - Jira API will reject")
                
                # Task without Story parent 
                elif issue_type == 'task' and not parent_summary:
                    validation_errors.append(f"Task '{proposal.get('summary')}' missing Story parent - Jira API will reject")
                
                # Subtask without Task parent (CRITICAL - API always rejects)
                elif issue_type in ['subtask', 'sub-task', 'sottotask'] and not parent_summary:
                    validation_errors.append(f"CRITICAL: Subtask '{proposal.get('summary')}' missing Task parent - Jira API will reject with 400 error")
        
        if validation_errors:
            logger.error("JIRA HIERARCHY VALIDATION ERRORS (API will likely reject these):")
            for error in validation_errors:
                logger.error(f"  - {error}")
            # Continue with warnings - let API provide definitive rejection

        # Process approved proposals in hierarchical order
        for idx, proposal in approved_proposals:
            try:
                if proposal['action'] == "create":
                    parent_key = None
                    epic_key = None
                    
                    # JIRA API-COMPLIANT PARENT RESOLUTION: Epic → Story → Task → Subtask
                    resolved_parent_key = None
                    issue_type = proposal['issue_type'].lower()
                    
                    if proposal.get('parent_summary'):
                        parent_summary = proposal['parent_summary']
                        
                        # PRIORITY 1: Check if parent was just created in this batch
                        if parent_summary in created_tickets:
                            resolved_parent_key = created_tickets[parent_summary]
                            logger.info(f"Using newly created parent: {resolved_parent_key}")
                        else:
                            # PRIORITY 2: Search in existing structure based on STRICT Jira hierarchy
                            if issue_type == 'story':
                                # Story → Epic (ONLY valid relationship for Stories)
                                resolved_parent_key = await jira_client.find_matching_epic(parent_summary, hierarchical_structure)
                                if resolved_parent_key:
                                    logger.info(f"Found existing Epic parent for Story: {resolved_parent_key}")
                                    
                            elif issue_type == 'task':
                                # Task → Story (NEVER Task → Epic, API will reject!)
                                for story_key, story in hierarchical_structure["stories"].items():
                                    if story["summary"].lower().strip() == parent_summary.lower().strip():
                                        resolved_parent_key = story_key
                                        logger.info(f"Found existing Story parent for Task: {resolved_parent_key}")
                                        break
                                
                                if not resolved_parent_key:
                                    logger.error(f"HIERARCHY ERROR: Task '{proposal['summary']}' has parent_summary '{parent_summary}' but no matching Story found!")
                                    logger.error("Tasks MUST have Story parents (not Epic parents) for Jira API compliance")
                                    
                            elif issue_type in ['subtask', 'sub-task', 'sottotask']:
                                # Subtask → Task (NEVER Subtask → Story/Epic, API will reject!)
                                for task_key, task in hierarchical_structure["tasks"].items():
                                    if task["summary"].lower().strip() == parent_summary.lower().strip():
                                        resolved_parent_key = task_key
                                        logger.info(f"Found existing Task parent for Subtask: {resolved_parent_key}")
                                        break
                                
                                if not resolved_parent_key:
                                    logger.error(f"HIERARCHY ERROR: Subtask '{proposal['summary']}' has parent_summary '{parent_summary}' but no matching Task found!")
                                    logger.error("Subtasks MUST have Task parents (not Story/Epic parents) for Jira API compliance")
                    
                    # CRITICAL: Validate hierarchy before API call
                    if not resolved_parent_key and issue_type in ['subtask', 'sub-task', 'sottotask']:
                        logger.error(f"CRITICAL: Cannot create Subtask without valid Task parent. Skipping '{proposal['summary']}'")
                        results.append({
                            "index": idx,
                            "action": "create", 
                            "success": False,
                            "error": "Subtask requires Task parent - hierarchy validation failed",
                            "hierarchy_issue": "Missing Task parent for Subtask"
                        })
                        continue
                    
                    logger.info(f"Creating {proposal['issue_type']} ticket: {proposal['summary']} (parent: {resolved_parent_key})")
                    ticket_key = await jira_client.create_ticket(
                        project_key=jira_project_key,
                        issue_type=proposal['issue_type'],
                        summary=proposal['summary'],
                        description=proposal['description'],
                        parent_key=resolved_parent_key,
                        story_points=proposal.get('story_points'),
                        priority=proposal.get('priority')
                    )
                    
                    if ticket_key:
                        # Track created ticket for future parent resolution
                        created_tickets[proposal['summary']] = ticket_key
                        logger.info(f"Successfully created ticket: {ticket_key}")
                        
                        # Parent relationships are now handled directly in create_ticket via the parent field
                        # No additional linking needed as parent field creates the hierarchy
                    
                    results.append({
                        "index": idx,
                        "action": "create",
                        "success": ticket_key is not None,
                        "ticket_key": ticket_key,
                        "parent_key": resolved_parent_key,
                        "issue_type": proposal['issue_type'],
                        "summary": proposal['summary'],
                        "hierarchy_level": "Epic" if proposal['issue_type'].lower() == 'epic' else 
                                         "Story" if proposal['issue_type'].lower() in ['story', 'task'] else 
                                         "Subtask"
                    })

                elif proposal['action'] == "modify" and proposal.get('ticket_key'):
                    logger.info(f"Updating ticket: {proposal['ticket_key']}")
                    success = await jira_client.update_ticket(
                        ticket_key=proposal['ticket_key'],
                        summary=proposal['summary'],
                        description=proposal['description']
                    )
                    results.append({
                        "index": idx,
                        "action": "modify",
                        "success": success,
                        "ticket_key": proposal['ticket_key']
                    })

                elif proposal['action'] == "reuse_existing":
                    logger.info(f"Reusing existing ticket: {proposal.get('ticket_key', 'N/A')}")
                    results.append({
                        "index": idx,
                        "action": "reuse_existing",
                        "success": True,
                        "ticket_key": proposal.get('ticket_key'),
                        "message": "Existing ticket covers this requirement"
                    })

            except Exception as e:
                logger.error(f"Error processing proposal {idx}: {e}")
                results.append({
                    "index": idx,
                    "action": proposal['action'],
                    "success": False,
                    "error": str(e)
                })

        # Update analysis status
        status = "approved" if len(approval.approved_indices) == len(proposed_changes) else "partially_approved"

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                'UPDATE meeting_analyses SET status = ?, processed_at = ? WHERE id = ?',
                (status, datetime.now(timezone.utc).isoformat(), analysis_id)
            )
            await db.commit()

        return {"success": True, "results": results}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving proposals: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@api_router.put("/analysis/{analysis_id}/modify")
async def modify_proposal(analysis_id: str, modification: ModifyProposalRequest):
    """Modify a proposal before approval"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM meeting_analyses WHERE id = ?', (analysis_id,)) as cursor:
                row = await cursor.fetchone()

                if not row:
                    raise HTTPException(status_code=404, detail="Analysis not found")

                proposed_changes = json.loads(row['proposed_changes'])

                if modification.index >= len(proposed_changes):
                    raise HTTPException(status_code=400, detail="Invalid proposal index")

                if modification.summary:
                    proposed_changes[modification.index]['summary'] = modification.summary
                if modification.description:
                    proposed_changes[modification.index]['description'] = modification.description

                await db.execute(
                    'UPDATE meeting_analyses SET proposed_changes = ? WHERE id = ?',
                    (json.dumps(proposed_changes), analysis_id)
                )
                await db.commit()

        return {"success": True, "message": "Proposal updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error modifying proposal: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.delete("/analysis/{analysis_id}")
async def delete_analysis(analysis_id: str):
    """Delete/reject an analysis"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                'UPDATE meeting_analyses SET status = ? WHERE id = ?',
                ('rejected', analysis_id)
            )
            await db.commit()

            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Analysis not found")

        return {"success": True, "message": "Analysis rejected"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    await init_db()
    logger.info("Application started successfully")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Application shutting down")
