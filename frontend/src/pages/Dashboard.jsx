import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { CheckCircle2, Clock, XCircle, PlusCircle, Settings } from 'lucide-react';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function Dashboard() {
  const [stats, setStats] = useState({
    total: 0,
    pending: 0,
    approved: 0,
    rejected: 0,
  });
  const [isConfigured, setIsConfigured] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const fetchDashboardData = async () => {
    try {
      // Check if Jira is configured
      const configRes = await axios.get(`${API}/jira/config`);
      setIsConfigured(configRes.data.configured);

      // Fetch analyses
      const analysesRes = await axios.get(`${API}/analysis`);
      const analyses = analysesRes.data.analyses || [];

      setStats({
        total: analyses.length,
        pending: analyses.filter(a => a.status === 'pending').length,
        approved: analyses.filter(a => a.status === 'approved' || a.status === 'partially_approved').length,
        rejected: analyses.filter(a => a.status === 'rejected').length,
      });
    } catch (error) {
      console.error('Error fetching dashboard data:', error);
      toast.error('Failed to load dashboard data');
    } finally {
      setLoading(false);
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
    <div data-testid="dashboard-page">
      <div className="mb-8">
        <h1 className="text-4xl font-bold text-slate-900 mb-2">Dashboard</h1>
        <p className="text-slate-600">Monitor your Jira meeting synchronization</p>
      </div>

      {!isConfigured && (
        <Card className="mb-6 border-l-4 border-l-amber-500 bg-amber-50">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-amber-900 mb-1">Configuration Required</h3>
                <p className="text-sm text-amber-700">Please configure your Jira credentials to get started</p>
              </div>
              <Link to="/config">
                <Button data-testid="configure-jira-btn" className="bg-amber-600 hover:bg-amber-700">
                  <Settings className="w-4 h-4 mr-2" />
                  Configure Now
                </Button>
              </Link>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <Card className="border-t-4 border-t-blue-500 hover:shadow-lg transition-shadow duration-200">
          <CardHeader>
            <CardTitle className="text-lg text-slate-700">Total Analyses</CardTitle>
          </CardHeader>
          <CardContent>
            <p data-testid="stat-total" className="text-4xl font-bold text-blue-600">{stats.total}</p>
          </CardContent>
        </Card>

        <Card className="border-t-4 border-t-amber-500 hover:shadow-lg transition-shadow duration-200">
          <CardHeader>
            <CardTitle className="text-lg text-slate-700 flex items-center">
              <Clock className="w-5 h-5 mr-2 text-amber-500" />
              Pending
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p data-testid="stat-pending" className="text-4xl font-bold text-amber-600">{stats.pending}</p>
          </CardContent>
        </Card>

        <Card className="border-t-4 border-t-green-500 hover:shadow-lg transition-shadow duration-200">
          <CardHeader>
            <CardTitle className="text-lg text-slate-700 flex items-center">
              <CheckCircle2 className="w-5 h-5 mr-2 text-green-500" />
              Approved
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p data-testid="stat-approved" className="text-4xl font-bold text-green-600">{stats.approved}</p>
          </CardContent>
        </Card>

        <Card className="border-t-4 border-t-red-500 hover:shadow-lg transition-shadow duration-200">
          <CardHeader>
            <CardTitle className="text-lg text-slate-700 flex items-center">
              <XCircle className="w-5 h-5 mr-2 text-red-500" />
              Rejected
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p data-testid="stat-rejected" className="text-4xl font-bold text-red-600">{stats.rejected}</p>
          </CardContent>
        </Card>
      </div>

      <Card className="shadow-xl border-slate-200">
        <CardHeader>
          <CardTitle className="text-2xl">Quick Actions</CardTitle>
          <CardDescription>Start analyzing your meeting minutes</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col sm:flex-row gap-4">
            <Link to="/new-analysis" className="flex-1">
              <Button data-testid="new-analysis-btn" className="w-full h-24 text-lg bg-blue-600 hover:bg-blue-700">
                <PlusCircle className="w-6 h-6 mr-3" />
                Create New Analysis
              </Button>
            </Link>
            <Link to="/history" className="flex-1">
              <Button data-testid="view-history-btn" variant="outline" className="w-full h-24 text-lg border-2 border-slate-300 hover:bg-slate-50">
                View Analysis History
              </Button>
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}