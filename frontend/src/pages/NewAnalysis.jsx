import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Check, ChevronsUpDown } from 'lucide-react';
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
  const [projects, setProjects] = useState([]);
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [clientNames, setClientNames] = useState([]);
  const [projectNames, setProjectNames] = useState([]);
  const [loadingOptions, setLoadingOptions] = useState(true);
  const [openClient, setOpenClient] = useState(false);
  const [openProject, setOpenProject] = useState(false);

  const fetchProjects = async () => {
    try {
      const response = await axios.get(`${API}/jira/projects`);
      setProjects(response.data.projects);
    } catch (error) {
      console.error('Error fetching projects:', error);
      toast.error('Failed to load Jira projects. Please check your Jira configuration.');
    } finally {
      setLoadingProjects(false);
    }
  };

  const fetchClientNames = async () => {
    try {
      const response = await axios.get(`${API}/analysis/client-names`);
      setClientNames(response.data.client_names);
    } catch (error) {
      console.error('Error fetching client names:', error);
      // Non mostriamo errore per questo, potrebbe essere vuoto
    }
  };

  const fetchProjectNames = async () => {
    try {
      const response = await axios.get(`${API}/analysis/project-names`);
      setProjectNames(response.data.project_names);
    } catch (error) {
      console.error('Error fetching project names:', error);
      // Non mostriamo errore per questo, potrebbe essere vuoto
    }
  };

  const fetchData = async () => {
    await Promise.all([
      fetchProjects(),
      fetchClientNames(),
      fetchProjectNames()
    ]);
    setLoadingOptions(false);
  };

  useEffect(() => {
    fetchData();
  }, []);

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
                <Select 
                  value={formData.jira_project_key} 
                  onValueChange={(value) => setFormData({ ...formData, jira_project_key: value })}
                  disabled={loadingProjects}
                >
                  <SelectTrigger className="h-12">
                    <SelectValue placeholder={loadingProjects ? "Loading projects..." : "Select a project"} />
                  </SelectTrigger>
                  <SelectContent>
                    {projects.map((project) => (
                      <SelectItem key={project.key} value={project.key}>
                        <div className="flex flex-col">
                          <span className="font-medium">{project.key}</span>
                          <span className="text-sm text-slate-500">{project.name}</span>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-sm text-slate-500">Select your Jira project from the available options</p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="client_name">Client Name *</Label>
                <Popover open={openClient} onOpenChange={setOpenClient}>
                  <PopoverTrigger asChild>
                    <Button
                      variant="outline"
                      role="combobox"
                      aria-expanded={openClient}
                      className="h-12 w-full justify-between"
                    >
                      {formData.client_name || "Select or type client name..."}
                      <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-full p-0">
                    <Command>
                      <CommandInput 
                        placeholder="Search or type client name..." 
                        value={formData.client_name}
                        onValueChange={(value) => setFormData({ ...formData, client_name: value })}
                      />
                      <CommandList>
                        <CommandEmpty>No client found. Press Enter to use current input.</CommandEmpty>
                        <CommandGroup>
                          {clientNames.map((name) => (
                            <CommandItem
                              key={name}
                              value={name}
                              onSelect={(currentValue) => {
                                setFormData({ ...formData, client_name: currentValue });
                                setOpenClient(false);
                              }}
                            >
                              <Check
                                className={`mr-2 h-4 w-4 ${
                                  formData.client_name === name ? "opacity-100" : "opacity-0"
                                }`}
                              />
                              {name}
                            </CommandItem>
                          ))}
                        </CommandGroup>
                      </CommandList>
                    </Command>
                  </PopoverContent>
                </Popover>
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="project_name">Project Name *</Label>
              <Popover open={openProject} onOpenChange={setOpenProject}>
                <PopoverTrigger asChild>
                  <Button
                    variant="outline"
                    role="combobox"
                    aria-expanded={openProject}
                    className="h-12 w-full justify-between"
                  >
                    {formData.project_name || "Select or type project name..."}
                    <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-full p-0">
                  <Command>
                    <CommandInput 
                      placeholder="Search or type project name..." 
                      value={formData.project_name}
                      onValueChange={(value) => setFormData({ ...formData, project_name: value })}
                    />
                    <CommandList>
                      <CommandEmpty>No project found. Press Enter to use current input.</CommandEmpty>
                      <CommandGroup>
                        {projectNames.map((name) => (
                          <CommandItem
                            key={name}
                            value={name}
                            onSelect={(currentValue) => {
                              setFormData({ ...formData, project_name: currentValue });
                              setOpenProject(false);
                            }}
                          >
                            <Check
                              className={`mr-2 h-4 w-4 ${
                                formData.project_name === name ? "opacity-100" : "opacity-0"
                              }`}
                            />
                            {name}
                          </CommandItem>
                        ))}
                      </CommandGroup>
                    </CommandList>
                  </Command>
                </PopoverContent>
              </Popover>
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