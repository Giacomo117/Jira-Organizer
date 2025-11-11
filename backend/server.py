from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
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
from openai import AsyncAzureOpenAI

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

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

class JiraConnectionTest(BaseModel):
    success: bool
    message: str

class ProposedTicket(BaseModel):
    action: str  # "create" or "modify"
    ticket_key: Optional[str] = None  # For modifications
    issue_type: str  # Story, Task, Bug, etc.
    summary: str
    description: str
    current_summary: Optional[str] = None  # For modifications
    current_description: Optional[str] = None  # For modifications
    reasoning: str

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
    def __init__(self, domain: str, email: str, api_token: str):
        self.domain = domain
        self.base_url = f"https://{domain}/rest/api/3"
        self.email = email
        self.api_token = api_token
        
        # Create basic auth header
        auth_str = f"{email}:{api_token}"
        auth_bytes = auth_str.encode('ascii')
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
                async with session.get(
                    f"{self.base_url}/myself",
                    headers=self.headers
                ) as response:
                    return response.status == 200
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
                    jql = f"project={project_key}"
                    params = {
                        "jql": jql,
                        "startAt": start_at,
                        "maxResults": max_results,
                        "fields": "summary,description,status,issuetype,key"
                    }
                    
                    async with session.get(
                        f"{self.base_url}/search",
                        headers=self.headers,
                        params=params
                    ) as response:
                        if response.status != 200:
                            logger.error(f"Failed to fetch tickets: {response.status}")
                            break
                        
                        data = await response.json()
                        issues = data.get('issues', [])
                        all_tickets.extend(issues)
                        
                        # Check if there are more results
                        if len(issues) < max_results:
                            break
                        
                        start_at += max_results
            
            return all_tickets
        except Exception as e:
            logger.error(f"Error fetching project tickets: {e}")
            return []
    
    async def create_ticket(self, project_key: str, issue_type: str, summary: str, description: str) -> Optional[str]:
        """Create a new Jira ticket"""
        try:
            payload = {
                "fields": {
                    "project": {"key": project_key},
                    "summary": summary,
                    "description": {
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
                    },
                    "issuetype": {"name": issue_type}
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/issue",
                    headers=self.headers,
                    json=payload
                ) as response:
                    if response.status in [200, 201]:
                        data = await response.json()
                        return data.get('key')
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to create ticket: {response.status} - {error_text}")
                        return None
        except Exception as e:
            logger.error(f"Error creating ticket: {e}")
            return None
    
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

# ==================== LLM Analysis Service ====================

async def analyze_meeting_with_llm(meeting_minutes: str, project_key: str, existing_tickets: List[Dict]) -> List[ProposedTicket]:
    """Use Azure OpenAI to analyze meeting minutes and propose Jira changes"""
    try:
        # Format existing tickets for the LLM
        tickets_summary = "\n".join([
            f"- {ticket['key']}: [{ticket['fields']['issuetype']['name']}] {ticket['fields']['summary']}\n  Description: {ticket['fields'].get('description', {}).get('content', [{}])[0].get('content', [{}])[0].get('text', 'No description')[:200]}"
            for ticket in existing_tickets[:50]  # Limit to avoid token overflow
        ])

        system_message = """You are a Jira project management assistant. Your task is to analyze meeting minutes and compare them with existing Jira tickets to identify:
1. New tasks, stories, or bugs that should be created
2. Existing tickets that need to be updated based on meeting decisions

You must respond ONLY with a valid JSON array of proposed changes. Each change must have this exact structure:
{
  "action": "create" or "modify",
  "ticket_key": "PROJ-123" (only for modify actions),
  "issue_type": "Story" or "Task" or "Bug",
  "summary": "Brief title",
  "description": "Detailed description",
  "current_summary": "existing summary" (only for modify actions),
  "current_description": "existing description" (only for modify actions),
  "reasoning": "Why this change is needed based on the meeting"
}

IMPORTANT: Respond with ONLY a JSON array, no additional text or explanation."""

        user_prompt = f"""Project: {project_key}

Existing Tickets:
{tickets_summary if tickets_summary else 'No existing tickets'}

Meeting Minutes:
{meeting_minutes}

Analyze the meeting minutes and propose changes as a JSON array."""

        # Initialize Azure OpenAI client
        azure_client = AsyncAzureOpenAI(
            api_key=os.environ.get('AZURE_OPENAI_API_KEY'),
            api_version=os.environ.get('AZURE_OPENAI_API_VERSION', '2024-02-15-preview'),
            azure_endpoint=os.environ.get('AZURE_OPENAI_ENDPOINT')
        )

        # Get deployment name from environment
        deployment_name = os.environ.get('AZURE_OPENAI_DEPLOYMENT_NAME', 'gpt-4')

        # Send message to Azure OpenAI
        response = await azure_client.chat.completions.create(
            model=deployment_name,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=4000
        )

        response_text = response.choices[0].message.content
        logger.info(f"Azure OpenAI Response: {response_text}")

        # Parse response
        # Remove markdown code blocks if present
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            response_text = "\n".join(lines[1:-1]) if len(lines) > 2 else response_text
            response_text = response_text.replace("```json", "").replace("```", "")

        proposals_data = json.loads(response_text.strip())

        # Convert to ProposedTicket objects
        proposals = [ProposedTicket(**item) for item in proposals_data]

        return proposals

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON: {e}")
        logger.error(f"Response was: {response_text if 'response_text' in locals() else 'No response'}")
        return []
    except Exception as e:
        logger.error(f"Error in Azure OpenAI analysis: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []

# ==================== API Routes ====================

@api_router.get("/")
async def root():
    return {"message": "Jira Meeting Sync API"}

# Jira Configuration endpoints
@api_router.post("/jira/config")
async def save_jira_config(config: JiraConfigCreate):
    """Save Jira configuration"""
    try:
        # Delete existing config (single-user setup)
        await db.jira_configs.delete_many({})
        
        config_obj = JiraConfig(**config.model_dump())
        doc = config_obj.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        
        await db.jira_configs.insert_one(doc)
        
        return {"success": True, "message": "Jira configuration saved successfully"}
    except Exception as e:
        logger.error(f"Error saving Jira config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/jira/config")
async def get_jira_config():
    """Get saved Jira configuration (without API token for security)"""
    try:
        config = await db.jira_configs.find_one({}, {"_id": 0})
        
        if not config:
            return {"configured": False}
        
        # Don't return the API token
        return {
            "configured": True,
            "jira_domain": config.get('jira_domain'),
            "jira_email": config.get('jira_email')
        }
    except Exception as e:
        logger.error(f"Error fetching Jira config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/jira/test-connection", response_model=JiraConnectionTest)
async def test_jira_connection():
    """Test connection to Jira"""
    try:
        config = await db.jira_configs.find_one({}, {"_id": 0})
        
        if not config:
            return JiraConnectionTest(
                success=False,
                message="No Jira configuration found. Please configure Jira first."
            )
        
        jira_client = JiraAPIClient(
            domain=config['jira_domain'],
            email=config['jira_email'],
            api_token=config['jira_api_token']
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

# Meeting Analysis endpoints
@api_router.post("/analysis/create")
async def create_analysis(analysis_request: MeetingAnalysisCreate):
    """Create a new meeting analysis"""
    try:
        # Get Jira config
        config = await db.jira_configs.find_one({}, {"_id": 0})
        if not config:
            raise HTTPException(status_code=400, detail="Jira not configured")
        
        # Initialize Jira client
        jira_client = JiraAPIClient(
            domain=config['jira_domain'],
            email=config['jira_email'],
            api_token=config['jira_api_token']
        )
        
        # Fetch existing tickets
        existing_tickets = await jira_client.get_project_tickets(analysis_request.jira_project_key)
        
        # Analyze with LLM
        proposals = await analyze_meeting_with_llm(
            meeting_minutes=analysis_request.meeting_minutes,
            project_key=analysis_request.jira_project_key,
            existing_tickets=existing_tickets
        )
        
        # Create analysis record
        analysis = MeetingAnalysis(
            **analysis_request.model_dump(),
            proposed_changes=proposals
        )
        
        doc = analysis.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        if doc.get('processed_at'):
            doc['processed_at'] = doc['processed_at'].isoformat()
        
        await db.meeting_analyses.insert_one(doc)
        
        return {"success": True, "analysis_id": analysis.id, "proposals_count": len(proposals)}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/analysis/{analysis_id}")
async def get_analysis(analysis_id: str):
    """Get analysis by ID"""
    try:
        analysis = await db.meeting_analyses.find_one({"id": analysis_id}, {"_id": 0})
        
        if not analysis:
            raise HTTPException(status_code=404, detail="Analysis not found")
        
        return analysis
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/analysis")
async def get_all_analyses():
    """Get all analyses"""
    try:
        analyses = await db.meeting_analyses.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
        return {"analyses": analyses}
    except Exception as e:
        logger.error(f"Error fetching analyses: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/analysis/{analysis_id}/approve")
async def approve_proposals(analysis_id: str, approval: ApprovalRequest):
    """Approve and execute proposals"""
    try:
        # Get analysis
        analysis_doc = await db.meeting_analyses.find_one({"id": analysis_id}, {"_id": 0})
        if not analysis_doc:
            raise HTTPException(status_code=404, detail="Analysis not found")
        
        analysis = MeetingAnalysis(**analysis_doc)
        
        # Get Jira config
        config = await db.jira_configs.find_one({}, {"_id": 0})
        if not config:
            raise HTTPException(status_code=400, detail="Jira not configured")
        
        jira_client = JiraAPIClient(
            domain=config['jira_domain'],
            email=config['jira_email'],
            api_token=config['jira_api_token']
        )
        
        results = []
        
        # Process approved proposals
        for idx in approval.approved_indices:
            if idx >= len(analysis.proposed_changes):
                continue
            
            proposal = analysis.proposed_changes[idx]
            
            if proposal.action == "create":
                ticket_key = await jira_client.create_ticket(
                    project_key=analysis.jira_project_key,
                    issue_type=proposal.issue_type,
                    summary=proposal.summary,
                    description=proposal.description
                )
                results.append({
                    "index": idx,
                    "action": "create",
                    "success": ticket_key is not None,
                    "ticket_key": ticket_key
                })
            
            elif proposal.action == "modify" and proposal.ticket_key:
                success = await jira_client.update_ticket(
                    ticket_key=proposal.ticket_key,
                    summary=proposal.summary,
                    description=proposal.description
                )
                results.append({
                    "index": idx,
                    "action": "modify",
                    "success": success,
                    "ticket_key": proposal.ticket_key
                })
        
        # Update analysis status
        status = "approved" if len(approval.approved_indices) == len(analysis.proposed_changes) else "partially_approved"
        
        await db.meeting_analyses.update_one(
            {"id": analysis_id},
            {"$set": {
                "status": status,
                "processed_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        return {"success": True, "results": results}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving proposals: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.put("/analysis/{analysis_id}/modify")
async def modify_proposal(analysis_id: str, modification: ModifyProposalRequest):
    """Modify a proposal before approval"""
    try:
        analysis = await db.meeting_analyses.find_one({"id": analysis_id}, {"_id": 0})
        if not analysis:
            raise HTTPException(status_code=404, detail="Analysis not found")
        
        if modification.index >= len(analysis['proposed_changes']):
            raise HTTPException(status_code=400, detail="Invalid proposal index")
        
        update_fields = {}
        if modification.summary:
            update_fields[f"proposed_changes.{modification.index}.summary"] = modification.summary
        if modification.description:
            update_fields[f"proposed_changes.{modification.index}.description"] = modification.description
        
        await db.meeting_analyses.update_one(
            {"id": analysis_id},
            {"$set": update_fields}
        )
        
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
        result = await db.meeting_analyses.update_one(
            {"id": analysis_id},
            {"$set": {"status": "rejected"}}
        )
        
        if result.modified_count == 0:
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

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()