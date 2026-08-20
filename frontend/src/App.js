import { BrowserRouter, Routes, Route } from "react-router-dom";
import Sidebar from "@/components/Sidebar";
import ProjectsList from "@/pages/ProjectsList";
import ProjectDetail from "@/pages/ProjectDetail";
import Repository from "@/pages/Repository";
import Admin from "@/pages/Admin";
import Indices from "@/pages/Indices";
import { Toaster } from "@/components/ui/sonner";

function App() {
  return (
    <BrowserRouter>
      <div className="flex min-h-screen bg-white">
        <Sidebar />
        <main className="flex-1 min-w-0">
          <Routes>
            <Route path="/" element={<ProjectsList />} />
            <Route path="/projects/:id" element={<ProjectDetail />} />
            <Route path="/repository" element={<Repository />} />
            <Route path="/admin" element={<Admin />} />
            <Route path="/indices" element={<Indices />} />
          </Routes>
        </main>
      </div>
      <Toaster position="top-right" richColors closeButton />
    </BrowserRouter>
  );
}

export default App;
