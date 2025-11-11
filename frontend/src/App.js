import { BrowserRouter, Routes, Route } from "react-router-dom";
import "@/App.css";
import Dashboard from "@/pages/Dashboard";
import Configuration from "@/pages/Configuration";
import NewAnalysis from "@/pages/NewAnalysis";
import ReviewProposals from "@/pages/ReviewProposals";
import History from "@/pages/History";
import Layout from "@/components/Layout";

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="/config" element={<Configuration />} />
            <Route path="/new-analysis" element={<NewAnalysis />} />
            <Route path="/review/:id" element={<ReviewProposals />} />
            <Route path="/history" element={<History />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </div>
  );
}

export default App;