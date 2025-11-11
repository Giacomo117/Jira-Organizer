import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { Eye, Calendar, FileText } from 'lucide-react';
import { format } from 'date-fns';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function History() {
  const [analyses, setAnalyses] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchHistory();
  }, []);

  const fetchHistory = async () => {
    try {
      const response = await axios.get(`${API}/analysis`);
      setAnalyses(response.data.analyses || []);
    } catch (error) {
      console.error('Error fetching history:', error);
      toast.error('Failed to load history');
    } finally {
      setLoading(false);
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'pending':
        return 'bg-amber-100 text-amber-800 border-amber-300';
      case 'approved':
      case 'partially_approved':
        return 'bg-green-100 text-green-800 border-green-300';
      case 'rejected':
        return 'bg-red-100 text-red-800 border-red-300';
      default:
        return 'bg-slate-100 text-slate-800 border-slate-300';
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div data-testid="history-page">
      <div className="mb-8">
        <h1 className="text-4xl font-bold text-slate-900 mb-2">Analysis History</h1>
        <p className="text-slate-600">View all past meeting analyses and their status</p>
      </div>

      {analyses.length === 0 ? (
        <Card className="shadow-xl">
          <CardContent className="py-12 text-center">
            <FileText className="w-16 h-16 text-slate-300 mx-auto mb-4" />
            <h3 className="text-xl font-semibold text-slate-700 mb-2">No analyses yet</h3>
            <p className="text-slate-500 mb-6">Create your first analysis to get started</p>
            <Link to="/new-analysis">
              <Button data-testid="create-first-analysis-btn" className="bg-blue-600 hover:bg-blue-700">
                Create New Analysis
              </Button>
            </Link>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {analyses.map((analysis) => (
            <Card key={analysis.id} data-testid={`history-item-${analysis.id}`} className="shadow-lg hover:shadow-xl transition-shadow duration-200">
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <CardTitle className="text-xl">{analysis.project_name}</CardTitle>
                      <Badge className={`border ${getStatusColor(analysis.status)}`}>
                        {analysis.status.replace('_', ' ').toUpperCase()}
                      </Badge>
                    </div>
                    <div className="flex items-center gap-4 text-sm text-slate-600">
                      <span className="font-semibold">{analysis.jira_project_key}</span>
                      <span>•</span>
                      <span>{analysis.client_name}</span>
                      <span>•</span>
                      <span className="flex items-center">
                        <Calendar className="w-4 h-4 mr-1" />
                        {format(new Date(analysis.created_at), 'MMM d, yyyy HH:mm')}
                      </span>
                    </div>
                  </div>
                  
                  <Link to={`/review/${analysis.id}`}>
                    <Button data-testid={`review-btn-${analysis.id}`} size="sm" className="bg-blue-600 hover:bg-blue-700">
                      <Eye className="w-4 h-4 mr-2" />
                      {analysis.status === 'pending' ? 'Review' : 'View Details'}
                    </Button>
                  </Link>
                </div>
              </CardHeader>
              <CardContent>
                <div className="bg-slate-50 p-4 rounded-lg border border-slate-200">
                  <p className="text-sm text-slate-700 line-clamp-3">{analysis.meeting_minutes}</p>
                </div>
                <div className="mt-3 text-sm text-slate-600">
                  <strong>{analysis.proposed_changes.length}</strong> proposals generated
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}