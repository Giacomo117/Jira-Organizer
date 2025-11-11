# Jira Meeting Organizer

An intelligent system that analyzes meeting minutes and automatically synchronizes them with Jira tickets using Azure OpenAI.

## 🎯 Overview

This application solves a common problem in teams: synchronizing meeting outcomes with project status in Jira. It uses Azure OpenAI to analyze meeting minutes, compare them with existing Jira tickets, and propose new tickets or modifications. A human-in-the-loop review process ensures all changes are verified before being applied to Jira.

### Key Features

- **AI-Powered Analysis**: Uses Azure OpenAI to understand meeting minutes and extract actionable items
- **Smart Comparison**: Compares meeting outcomes with existing Jira tickets to identify new tasks and modifications
- **Human Review**: All AI proposals are reviewed and can be edited before being applied
- **Jira Integration**: Seamlessly creates and updates tickets via the Jira REST API
- **Modern UI**: Beautiful, responsive interface built with React and shadcn/ui
- **Full History**: Track all analyses and their outcomes

## 🏗️ Architecture

### Components

1. **Frontend (React)**
   - Dashboard with statistics
   - Configuration page for Jira credentials
   - Meeting analysis form
   - Proposal review interface with diff view
   - Analysis history

2. **Backend (FastAPI)**
   - RESTful API endpoints
   - Azure OpenAI integration
   - Jira REST API client
   - MongoDB for persistence

3. **Database (MongoDB)**
   - Stores Jira configurations
   - Stores meeting analyses and proposals
   - Tracks approval status

### Technology Stack

- **Frontend**: React 19, React Router, Axios, shadcn/ui, Tailwind CSS
- **Backend**: Python 3.9+, FastAPI, Motor (async MongoDB), Azure OpenAI SDK
- **Database**: MongoDB
- **AI**: Azure OpenAI (GPT-4)

## 📋 Prerequisites

- Python 3.9 or higher
- Node.js 16 or higher
- MongoDB (local or cloud instance)
- Azure OpenAI API access with a deployed model
- Jira Cloud account with API access

## 🚀 Setup Instructions

### 1. Clone the Repository

```bash
git clone https://github.com/Giacomo117/Jira-Organizer.git
cd Jira-Organizer
```

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file from template
cp .env.example .env
```

**Configure your `.env` file:**

```env
# MongoDB Configuration
MONGO_URL=mongodb://localhost:27017/
DB_NAME=jira_organizer

# Azure OpenAI Configuration
AZURE_OPENAI_API_KEY=your_azure_openai_api_key_here
AZURE_OPENAI_ENDPOINT=https://your-resource-name.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-02-15-preview
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4

# CORS Configuration
CORS_ORIGINS=http://localhost:3000
```

**Start the backend server:**

```bash
uvicorn server:app --reload --port 8000
```

The API will be available at `http://localhost:8000`

### 3. Frontend Setup

```bash
cd ../frontend

# Install dependencies
npm install
# or
yarn install

# Create .env file from template
cp .env.example .env
```

**Configure your `.env` file:**

```env
REACT_APP_BACKEND_URL=http://localhost:8000
```

**Start the development server:**

```bash
npm start
# or
yarn start
```

The application will open at `http://localhost:3000`

## 📖 Usage Guide

### 1. Configure Jira Credentials

1. Navigate to the **Configuration** page
2. Enter your Jira details:
   - **Jira Domain**: Your Atlassian domain (e.g., `yourcompany.atlassian.net`)
   - **Email**: Your Jira account email
   - **API Token**: Generate one at https://id.atlassian.com/manage-profile/security/api-tokens
3. Click **Test Connection** to verify
4. Save the configuration

### 2. Create a New Analysis

1. Go to **New Analysis** from the dashboard
2. Fill in the form:
   - **Jira Project Key**: The key of your Jira project (e.g., `PROJ`)
   - **Client Name**: The client or team name
   - **Project Name**: Descriptive name of the project
   - **Meeting Minutes**: Paste your meeting notes

Example meeting minutes:
```
Meeting Date: 2025-01-15
Attendees: John, Sarah, Mike

Discussion Points:
- Reviewed login feature implementation - looks good, ready to merge
- Bug discovered in payment flow when using PayPal - needs urgent fix
- Story PROJ-123 needs description updated based on client feedback about user permissions
- New requirement: Add analytics tracking to homepage
- Client requested dark mode feature for next sprint

Action Items:
- Fix PayPal bug (high priority)
- Update PROJ-123 description
- Create new story for analytics tracking
- Create new story for dark mode feature
```

3. Click **Analyze Meeting** - the AI will process your minutes

### 3. Review Proposals

After analysis, you'll see a list of proposed changes:

- **Create New**: New tickets the AI recommends creating
- **Modify Existing**: Updates to existing tickets based on meeting decisions

For each proposal, you can:
- ✅ **Select/Deselect**: Choose which proposals to apply
- ✏️ **Edit**: Modify the summary or description before applying
- 📝 **View Reasoning**: See why the AI proposed this change
- 🔍 **View Diff**: For modifications, see current vs. proposed values

### 4. Approve and Sync

1. Review all proposals carefully
2. Edit any that need adjustments
3. Deselect any you don't want to apply
4. Click **Approve & Sync to Jira**
5. The system will create/update the selected tickets in Jira

### 5. View History

The **History** page shows all past analyses with their status:
- Pending
- Approved
- Partially Approved
- Rejected

## 🔧 API Documentation

### Endpoints

#### Jira Configuration

- `POST /api/jira/config` - Save Jira configuration
- `GET /api/jira/config` - Get saved configuration (without API token)
- `POST /api/jira/test-connection` - Test Jira connection

#### Meeting Analysis

- `POST /api/analysis/create` - Create new analysis
- `GET /api/analysis` - Get all analyses
- `GET /api/analysis/{id}` - Get specific analysis
- `POST /api/analysis/{id}/approve` - Approve and execute proposals
- `PUT /api/analysis/{id}/modify` - Modify a proposal
- `DELETE /api/analysis/{id}` - Reject an analysis

### Example API Calls

**Create Analysis:**
```bash
curl -X POST http://localhost:8000/api/analysis/create \
  -H "Content-Type: application/json" \
  -d '{
    "jira_project_key": "PROJ",
    "client_name": "Acme Corp",
    "project_name": "Mobile App",
    "meeting_minutes": "Discussed new login feature..."
  }'
```

**Approve Proposals:**
```bash
curl -X POST http://localhost:8000/api/analysis/{analysis_id}/approve \
  -H "Content-Type: application/json" \
  -d '{
    "approved_indices": [0, 1, 2],
    "rejected_indices": []
  }'
```

## 🎨 Frontend Pages

### Dashboard
- Statistics overview (total, pending, approved, rejected analyses)
- Configuration status alert
- Quick action buttons

### Configuration
- Jira credentials form
- Connection test
- Secure storage (API token never exposed in responses)

### New Analysis
- Form for meeting details
- Large text area for meeting minutes
- Real-time validation

### Review Proposals
- Project information cards
- Proposal list with selection
- Inline editing
- Diff view for modifications
- Bulk approve/reject actions

### History
- Chronological list of all analyses
- Status badges
- Navigation to review details

## 🔒 Security Considerations

- API tokens are stored securely in MongoDB
- Tokens are never returned in API responses
- CORS is configured to allow only specified origins
- All Jira API calls use HTTPS with Basic Authentication
- Environment variables for sensitive configuration

## 🧪 Testing

The project includes comprehensive test coverage. Run tests with:

```bash
# Backend tests
cd backend
pytest

# Frontend tests
cd frontend
npm test
```

## 🐛 Troubleshooting

### MongoDB Connection Issues
- Ensure MongoDB is running: `mongod --version`
- Check connection string in `.env`
- For MongoDB Atlas, whitelist your IP address

### Azure OpenAI Issues
- Verify your API key is correct
- Ensure your deployment name matches the model in Azure
- Check that your endpoint URL is correct (should end with `.openai.azure.com/`)
- Verify your Azure subscription has sufficient quota

### Jira Connection Issues
- Verify your API token at https://id.atlassian.com/manage-profile/security/api-tokens
- Ensure your Jira domain is correct (just the domain, without https://)
- Check that your account has permission to create/edit tickets

### CORS Issues
- Ensure `CORS_ORIGINS` in backend `.env` includes your frontend URL
- Check that the frontend is using the correct `REACT_APP_BACKEND_URL`

## 📊 Database Schema

### jira_configs Collection
```javascript
{
  "id": "uuid",
  "jira_domain": "company.atlassian.net",
  "jira_email": "user@company.com",
  "jira_api_token": "encrypted_token",
  "created_at": "ISO8601 timestamp"
}
```

### meeting_analyses Collection
```javascript
{
  "id": "uuid",
  "jira_project_key": "PROJ",
  "client_name": "Client Name",
  "project_name": "Project Name",
  "meeting_minutes": "Full meeting text...",
  "proposed_changes": [
    {
      "action": "create",
      "issue_type": "Story",
      "summary": "Title",
      "description": "Details",
      "reasoning": "Why this is needed",
      "ticket_key": null,
      "current_summary": null,
      "current_description": null
    }
  ],
  "status": "pending",
  "created_at": "ISO8601 timestamp",
  "processed_at": "ISO8601 timestamp or null"
}
```

## 🤝 Contributing

Contributions are welcome! Please follow these guidelines:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Write/update tests
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License.

## 🙏 Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com/)
- UI components from [shadcn/ui](https://ui.shadcn.com/)
- AI powered by [Azure OpenAI](https://azure.microsoft.com/en-us/products/ai-services/openai-service)
- Icons from [Lucide](https://lucide.dev/)

## 📞 Support

For issues, questions, or contributions, please open an issue on GitHub.

---

**Note**: This system is designed to assist with Jira management but should not replace careful human review. Always verify AI-generated proposals before applying them to production projects.
