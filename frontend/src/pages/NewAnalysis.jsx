import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import { Loader2, FileText } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function NewAnalysis() {
  const navigate = useNavigate();
  const [formData, setFormData] = useState({
    jira_project_key: '',
    client_name: '',
    project_name: '',
    meeting_minutes: '',
  });
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      const response = await axios.post(`${API}/analysis/create`, formData);
      toast.success(`Analysis created! ${response.data.proposals_count} proposals generated`);
      navigate(`/review/${response.data.analysis_id}`);
    } catch (error) {
      console.error('Error creating analysis:', error);
      toast.error(error.response?.data?.detail || 'Failed to create analysis');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div data-testid="new-analysis-page">
      <div className="mb-8">
        <h1 className="text-4xl font-bold text-slate-900 mb-2">New Analysis</h1>
        <p className="text-slate-600">Analyze meeting minutes and generate Jira ticket proposals</p>
      </div>

      <Card className="shadow-xl max-w-4xl">
        <CardHeader>
          <CardTitle className="flex items-center text-2xl">
            <FileText className="w-6 h-6 mr-3 text-blue-600" />
            Meeting Details
          </CardTitle>
          <CardDescription>Provide the meeting context and minutes for AI analysis</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-2">
                <Label htmlFor="jira_project_key">Jira Project Key *</Label>
                <Input
                  id="jira_project_key"
                  data-testid="input-project-key"
                  placeholder="e.g., PROJ"
                  value={formData.jira_project_key}
                  onChange={(e) => setFormData({ ...formData, jira_project_key: e.target.value.toUpperCase() })}
                  required
                  className="h-12"
                />
                <p className="text-sm text-slate-500">The key identifier for your Jira project</p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="client_name">Client Name *</Label>
                <Input
                  id="client_name"
                  data-testid="input-client-name"
                  placeholder="e.g., Acme Corp"
                  value={formData.client_name}
                  onChange={(e) => setFormData({ ...formData, client_name: e.target.value })}
                  required
                  className="h-12"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="project_name">Project Name *</Label>
              <Input
                id="project_name"
                data-testid="input-project-name"
                placeholder="e.g., Mobile App Redesign"
                value={formData.project_name}
                onChange={(e) => setFormData({ ...formData, project_name: e.target.value })}
                required
                className="h-12"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="meeting_minutes">Meeting Minutes *</Label>
              <Textarea
                id="meeting_minutes"
                data-testid="input-meeting-minutes"
                placeholder="Paste your meeting minutes here...&#10;&#10;Example:&#10;- Discussed new login feature implementation&#10;- Bug found in payment flow - needs urgent fix&#10;- Story PROJ-123 needs description update based on client feedback&#10;- New task: Add analytics tracking to homepage"
                value={formData.meeting_minutes}
                onChange={(e) => setFormData({ ...formData, meeting_minutes: e.target.value })}
                required
                rows={12}
                className="resize-none font-mono text-sm"
              />
              <p className="text-sm text-slate-500">Include all relevant discussion points, decisions, and action items</p>
            </div>

            <div className="flex gap-4 pt-4">
              <Button
                type="submit"
                data-testid="analyze-btn"
                disabled={loading}
                className="flex-1 h-14 text-lg bg-blue-600 hover:bg-blue-700"
              >
                {loading ? (
                  <>
                    <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                    Analyzing with AI...
                  </>
                ) : (
                  'Analyze Meeting'
                )}
              </Button>
              
              <Button
                type="button"
                variant="outline"
                onClick={() => navigate('/')}
                className="h-14 px-8 border-2"
              >
                Cancel
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}