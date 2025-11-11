import { useState, useEffect } from 'react';
import axios from 'axios';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import { CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function Configuration() {
  const [formData, setFormData] = useState({
    jira_domain: '',
    jira_email: '',
    jira_api_token: '',
  });
  const [loading, setLoading] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);

  useEffect(() => {
    fetchConfig();
  }, []);

  const fetchConfig = async () => {
    try {
      const response = await axios.get(`${API}/jira/config`);
      if (response.data.configured) {
        setFormData(prev => ({
          ...prev,
          jira_domain: response.data.jira_domain,
          jira_email: response.data.jira_email,
        }));
      }
    } catch (error) {
      console.error('Error fetching config:', error);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setTestResult(null);

    try {
      await axios.post(`${API}/jira/config`, formData);
      toast.success('Configuration saved successfully!');
      // Test connection after saving
      testConnection();
    } catch (error) {
      console.error('Error saving config:', error);
      toast.error('Failed to save configuration');
    } finally {
      setLoading(false);
    }
  };

  const testConnection = async () => {
    setTesting(true);
    setTestResult(null);

    try {
      const response = await axios.post(`${API}/jira/test-connection`);
      setTestResult(response.data);
      if (response.data.success) {
        toast.success('Connection test successful!');
      } else {
        toast.error('Connection test failed');
      }
    } catch (error) {
      console.error('Error testing connection:', error);
      setTestResult({ success: false, message: 'Connection test failed' });
      toast.error('Connection test failed');
    } finally {
      setTesting(false);
    }
  };

  return (
    <div data-testid="configuration-page">
      <div className="mb-8">
        <h1 className="text-4xl font-bold text-slate-900 mb-2">Jira Configuration</h1>
        <p className="text-slate-600">Configure your Jira credentials for API access</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <Card className="shadow-xl">
            <CardHeader>
              <CardTitle>Connection Settings</CardTitle>
              <CardDescription>Enter your Jira credentials to enable synchronization</CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-6">
                <div className="space-y-2">
                  <Label htmlFor="jira_domain">Jira Domain</Label>
                  <Input
                    id="jira_domain"
                    data-testid="input-jira-domain"
                    placeholder="yourcompany.atlassian.net"
                    value={formData.jira_domain}
                    onChange={(e) => setFormData({ ...formData, jira_domain: e.target.value })}
                    required
                    className="h-12"
                  />
                  <p className="text-sm text-slate-500">Your Atlassian domain (without https://)</p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="jira_email">Email Address</Label>
                  <Input
                    id="jira_email"
                    data-testid="input-jira-email"
                    type="email"
                    placeholder="you@company.com"
                    value={formData.jira_email}
                    onChange={(e) => setFormData({ ...formData, jira_email: e.target.value })}
                    required
                    className="h-12"
                  />
                  <p className="text-sm text-slate-500">Your Atlassian account email</p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="jira_api_token">API Token</Label>
                  <Input
                    id="jira_api_token"
                    data-testid="input-jira-token"
                    type="password"
                    placeholder="Enter your Jira API token"
                    value={formData.jira_api_token}
                    onChange={(e) => setFormData({ ...formData, jira_api_token: e.target.value })}
                    required
                    className="h-12"
                  />
                  <p className="text-sm text-slate-500">
                    Generate at{' '}
                    <a
                      href="https://id.atlassian.com/manage-profile/security/api-tokens"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-600 hover:underline"
                    >
                      Atlassian API Tokens
                    </a>
                  </p>
                </div>

                <div className="flex gap-4 pt-4">
                  <Button
                    type="submit"
                    data-testid="save-config-btn"
                    disabled={loading}
                    className="flex-1 h-12 bg-blue-600 hover:bg-blue-700"
                  >
                    {loading ? (
                      <>
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        Saving...
                      </>
                    ) : (
                      'Save Configuration'
                    )}
                  </Button>
                  
                  <Button
                    type="button"
                    variant="outline"
                    data-testid="test-connection-btn"
                    onClick={testConnection}
                    disabled={testing || !formData.jira_domain}
                    className="h-12 border-2"
                  >
                    {testing ? (
                      <>
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        Testing...
                      </>
                    ) : (
                      'Test Connection'
                    )}
                  </Button>
                </div>
              </form>

              {testResult && (
                <div
                  data-testid="test-result"
                  className={`mt-6 p-4 rounded-lg flex items-start space-x-3 ${
                    testResult.success ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'
                  }`}
                >
                  {testResult.success ? (
                    <CheckCircle2 className="w-5 h-5 text-green-600 mt-0.5" />
                  ) : (
                    <AlertCircle className="w-5 h-5 text-red-600 mt-0.5" />
                  )}
                  <div>
                    <h4 className={`font-semibold ${
                      testResult.success ? 'text-green-900' : 'text-red-900'
                    }`}>
                      {testResult.success ? 'Connection Successful' : 'Connection Failed'}
                    </h4>
                    <p className={`text-sm ${
                      testResult.success ? 'text-green-700' : 'text-red-700'
                    }`}>
                      {testResult.message}
                    </p>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        <div>
          <Card className="shadow-xl">
            <CardHeader>
              <CardTitle>Setup Guide</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              <div>
                <h4 className="font-semibold text-slate-900 mb-2">Step 1: Get API Token</h4>
                <p className="text-slate-600">Visit Atlassian account settings and create a new API token</p>
              </div>
              <div>
                <h4 className="font-semibold text-slate-900 mb-2">Step 2: Enter Credentials</h4>
                <p className="text-slate-600">Fill in your Jira domain, email, and API token</p>
              </div>
              <div>
                <h4 className="font-semibold text-slate-900 mb-2">Step 3: Test Connection</h4>
                <p className="text-slate-600">Verify your credentials work correctly</p>
              </div>
              <div>
                <h4 className="font-semibold text-slate-900 mb-2">Step 4: Start Syncing</h4>
                <p className="text-slate-600">Begin analyzing meeting minutes and syncing with Jira</p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}