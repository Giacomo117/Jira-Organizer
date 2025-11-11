import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { toast } from 'sonner';
import { CheckCircle2, XCircle, Edit2, FileText, AlertCircle, Loader2, Layers, BookOpen, Settings, Wrench, Bug } from 'lucide-react';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function ReviewProposals() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedIndices, setSelectedIndices] = useState([]);
  const [processing, setProcessing] = useState(false);
  const [editingIndex, setEditingIndex] = useState(null);
  const [editForm, setEditForm] = useState({ summary: '', description: '' });

  const getIssueTypeIcon = (issueType) => {
    switch (issueType.toLowerCase()) {
      case 'epic':
        return <Layers className="w-4 h-4 text-purple-600" />;
      case 'story':
        return <BookOpen className="w-4 h-4 text-blue-600" />;
      case 'task':
        return <Settings className="w-4 h-4 text-green-600" />;
      case 'subtask':
      case 'sub-task':
        return <Wrench className="w-4 h-4 text-orange-600" />;
      case 'bug':
        return <Bug className="w-4 h-4 text-red-600" />;
      default:
        return <FileText className="w-4 h-4 text-gray-600" />;
    }
  };

  const getHierarchyIndent = (proposal) => {
    if (!proposal.parent_summary) return 0;
    if (proposal.issue_type.toLowerCase() === 'story') return 1; // Under Epic
    if (proposal.issue_type.toLowerCase() === 'task') return 1; // Under Epic or Story
    if (proposal.issue_type.toLowerCase() === 'subtask' || proposal.issue_type.toLowerCase() === 'sub-task') return 2; // Under Task/Story
    return 0;
  };

  const organizeProposalsByHierarchy = (proposals) => {
    // Sort by hierarchy: Epic first, then Story, then Task/Subtask
    const hierarchy = { 'epic': 0, 'story': 1, 'task': 2, 'subtask': 3, 'sub-task': 3, 'bug': 4 };
    return proposals.map((proposal, index) => ({ ...proposal, originalIndex: index }))
      .sort((a, b) => {
        const aLevel = hierarchy[a.issue_type.toLowerCase()] || 5;
        const bLevel = hierarchy[b.issue_type.toLowerCase()] || 5;
        if (aLevel !== bLevel) return aLevel - bLevel;
        // If same level, sort by parent relationship
        if (a.parent_summary && !b.parent_summary) return 1;
        if (!a.parent_summary && b.parent_summary) return -1;
        return 0;
      });
  };

  useEffect(() => {
    fetchAnalysis();
  }, [id]);

  const fetchAnalysis = async () => {
    try {
      const response = await axios.get(`${API}/analysis/${id}`);
      setAnalysis(response.data);
      // Select all by default
      setSelectedIndices(response.data.proposed_changes.map((_, idx) => idx));
    } catch (error) {
      console.error('Error fetching analysis:', error);
      toast.error('Failed to load analysis');
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async () => {
    if (selectedIndices.length === 0) {
      toast.error('Please select at least one proposal');
      return;
    }

    setProcessing(true);
    try {
      const response = await axios.post(`${API}/analysis/${id}/approve`, {
        approved_indices: selectedIndices,
        rejected_indices: [],
      });

      const successCount = response.data.results.filter(r => r.success).length;
      toast.success(`Successfully processed ${successCount} proposals!`);
      navigate('/history');
    } catch (error) {
      console.error('Error approving proposals:', error);
      toast.error('Failed to approve proposals');
    } finally {
      setProcessing(false);
    }
  };

  const handleReject = async () => {
    try {
      await axios.delete(`${API}/analysis/${id}`);
      toast.success('Analysis rejected');
      navigate('/history');
    } catch (error) {
      console.error('Error rejecting analysis:', error);
      toast.error('Failed to reject analysis');
    }
  };

  const toggleSelection = (index) => {
    setSelectedIndices(prev =>
      prev.includes(index) ? prev.filter(i => i !== index) : [...prev, index]
    );
  };

  const startEdit = (index, proposal) => {
    setEditingIndex(index);
    setEditForm({
      summary: proposal.summary,
      description: proposal.description,
    });
  };

  const saveEdit = async (index) => {
    try {
      await axios.put(`${API}/analysis/${id}/modify`, {
        index,
        ...editForm,
      });
      toast.success('Proposal updated');
      setEditingIndex(null);
      fetchAnalysis();
    } catch (error) {
      console.error('Error updating proposal:', error);
      toast.error('Failed to update proposal');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (!analysis) {
    return (
      <div className="text-center py-12">
        <AlertCircle className="w-16 h-16 text-red-500 mx-auto mb-4" />
        <h2 className="text-2xl font-bold text-slate-900">Analysis Not Found</h2>
      </div>
    );
  }

  return (
    <div data-testid="review-proposals-page">
      <div className="mb-8">
        <h1 className="text-4xl font-bold text-slate-900 mb-2">Review Proposals</h1>
        <p className="text-slate-600">Review and approve AI-generated Jira ticket proposals</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        <Card className="shadow-lg">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm text-slate-600">Project</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xl font-bold text-slate-900">{analysis.jira_project_key}</p>
            <p className="text-sm text-slate-600 mt-1">{analysis.project_name}</p>
          </CardContent>
        </Card>

        <Card className="shadow-lg">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm text-slate-600">Client</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xl font-bold text-slate-900">{analysis.client_name}</p>
          </CardContent>
        </Card>

        <Card className="shadow-lg">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm text-slate-600">Proposals</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xl font-bold text-slate-900">
              {selectedIndices.length} of {analysis.proposed_changes.length} selected
            </p>
          </CardContent>
        </Card>
      </div>

      <Card className="shadow-lg mb-6">
        <CardHeader>
          <CardTitle className="flex items-center">
            <FileText className="w-5 h-5 mr-2 text-blue-600" />
            Meeting Minutes
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="bg-slate-50 p-4 rounded-lg border border-slate-200">
            <p className="text-sm text-slate-700 whitespace-pre-wrap">{analysis.meeting_minutes}</p>
          </div>
        </CardContent>
      </Card>

      <div className="space-y-4 mb-6">
        {organizeProposalsByHierarchy(analysis.proposed_changes).map((proposal) => {
          const index = proposal.originalIndex;
          const indentLevel = getHierarchyIndent(proposal);
          return (
          <Card
            key={index}
            data-testid={`proposal-${index}`}
            className={`shadow-lg border-2 transition-all duration-200 ${
              selectedIndices.includes(index) ? 'border-blue-500 bg-blue-50/30' : 'border-slate-200'
            }`}
            style={{ marginLeft: `${indentLevel * 2}rem` }}
          >
            <CardHeader>
              <div className="flex items-start justify-between">
                <div className="flex items-start space-x-3 flex-1">
                  <Checkbox
                    data-testid={`checkbox-${index}`}
                    checked={selectedIndices.includes(index)}
                    onCheckedChange={() => toggleSelection(index)}
                    className="mt-1"
                  />
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      <Badge
                        variant={proposal.action === 'create' ? 'default' : 'secondary'}
                        className={proposal.action === 'create' ? 'bg-green-600' : 'bg-amber-600'}
                      >
                        {proposal.action === 'create' ? 'Create New' : 'Modify Existing'}
                      </Badge>
                      <Badge variant="outline" className="flex items-center gap-1">
                        {getIssueTypeIcon(proposal.issue_type)}
                        {proposal.issue_type}
                      </Badge>
                      {proposal.ticket_key && (
                        <Badge variant="outline" className="font-mono">{proposal.ticket_key}</Badge>
                      )}
                    </div>
                    
                    {editingIndex === index ? (
                      <div className="space-y-3 mt-3">
                        <Input
                          data-testid={`edit-summary-${index}`}
                          value={editForm.summary}
                          onChange={(e) => setEditForm({ ...editForm, summary: e.target.value })}
                          className="font-semibold"
                        />
                        <Textarea
                          data-testid={`edit-description-${index}`}
                          value={editForm.description}
                          onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                          rows={4}
                        />
                        <div className="flex gap-2">
                          <Button
                            size="sm"
                            data-testid={`save-edit-${index}`}
                            onClick={() => saveEdit(index)}
                            className="bg-green-600 hover:bg-green-700"
                          >
                            Save Changes
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => setEditingIndex(null)}
                          >
                            Cancel
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <h3 className="text-lg font-semibold text-slate-900 mb-2">{proposal.summary}</h3>
                        {proposal.parent_summary && (
                          <div className="mb-2 text-xs text-slate-500">
                            └─ Child of: <span className="font-semibold">{proposal.parent_summary}</span>
                          </div>
                        )}
                        {(proposal.story_points || proposal.priority) && (
                          <div className="flex gap-2 mb-2">
                            {proposal.story_points && (
                              <Badge variant="secondary" className="text-xs">
                                {proposal.story_points} SP
                              </Badge>
                            )}
                            {proposal.priority && (
                              <Badge variant="secondary" className={`text-xs ${
                                proposal.priority.toLowerCase() === 'high' ? 'bg-red-100 text-red-800' :
                                proposal.priority.toLowerCase() === 'medium' ? 'bg-yellow-100 text-yellow-800' :
                                'bg-green-100 text-green-800'
                              }`}>
                                {proposal.priority} Priority
                              </Badge>
                            )}
                          </div>
                        )}
                        <p className="text-sm text-slate-600 mb-3">{proposal.description}</p>
                        
                        {proposal.current_summary && (
                          <div className="bg-amber-50 border border-amber-200 rounded p-3 mb-3">
                            <p className="text-xs font-semibold text-amber-900 mb-1">Current Values:</p>
                            <p className="text-sm text-amber-800"><strong>Summary:</strong> {proposal.current_summary}</p>
                            <p className="text-sm text-amber-800 mt-1"><strong>Description:</strong> {proposal.current_description}</p>
                          </div>
                        )}
                        
                        <div className="bg-blue-50 border border-blue-200 rounded p-3">
                          <p className="text-xs font-semibold text-blue-900 mb-1">AI Reasoning:</p>
                          <p className="text-sm text-blue-800">{proposal.reasoning}</p>
                        </div>
                      </>
                    )}
                  </div>
                </div>
                
                {editingIndex !== index && (
                  <Button
                    size="sm"
                    variant="ghost"
                    data-testid={`edit-btn-${index}`}
                    onClick={() => startEdit(index, proposal)}
                    className="ml-2"
                  >
                    <Edit2 className="w-4 h-4" />
                  </Button>
                )}
              </div>
            </CardHeader>
          </Card>
        );
        })}
      </div>

      <Card className="shadow-xl border-slate-200">
        <CardContent className="pt-6">
          <div className="flex gap-4">
            <Button
              data-testid="approve-btn"
              onClick={handleApprove}
              disabled={processing || selectedIndices.length === 0}
              className="flex-1 h-14 text-lg bg-green-600 hover:bg-green-700"
            >
              {processing ? (
                <>
                  <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                  Processing...
                </>
              ) : (
                <>
                  <CheckCircle2 className="w-5 h-5 mr-2" />
                  Approve & Sync to Jira ({selectedIndices.length})
                </>
              )}
            </Button>
            
            <Button
              data-testid="reject-btn"
              variant="destructive"
              onClick={handleReject}
              disabled={processing}
              className="h-14 px-8"
            >
              <XCircle className="w-5 h-5 mr-2" />
              Reject All
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}