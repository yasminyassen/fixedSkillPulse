import { lazy, Suspense } from 'react';
import { Route, BrowserRouter as Router, Routes } from 'react-router-dom';

const GitHubCallback = lazy(() => import('./pages/GitHubCallback'));
const Login = lazy(() => import('./pages/Login'));
const NotFound = lazy(() => import('./pages/NotFound'));
const Register = lazy(() => import('./pages/register'));
const ForgotPassword = lazy(() => import('./pages/ForgotPassword'));
const ResetPassword = lazy(() => import('./pages/ResetPassword'));
const VerifyEmail = lazy(() => import('./pages/VerifyEmail'));
const RepositoryAnalysis = lazy(() => import('./pages/RepositoryAnalysis'));
const RoleSelection = lazy(() => import('./pages/RoleSelection'));

const CandidateEvaluation = lazy(() => import('./pages/Dashboard/CandidateEvaluation'));
const DeveloperLearning = lazy(() => import('./pages/Dashboard/DeveloperLearning'));
const DeveloperRequirements = lazy(() => import('./pages/Dashboard/DeveloperRequirements'));
const DeveloperSecurity = lazy(() => import('./pages/Dashboard/DeveloperSecurity'));
const DeveloperSkills = lazy(() => import('./pages/Dashboard/DeveloperSkills'));
const ManagerDashboard = lazy(() => import('./pages/Dashboard/ManagerDashboard'));
const ManagerSecurityDashboard = lazy(() => import('./pages/Dashboard/ManagerSecurityDashboard'));
const ManagerAccountSettings = lazy(() => import('./pages/Dashboard/ManagerAccountSettings'));
const ManagerProfile = lazy(() => import('./pages/Dashboard/ManagerProfile'));
const RecruiterDashboard = lazy(() => import('./pages/Dashboard/RecruiterDashboard'));
const RecruiterAccountSettings = lazy(() => import('./pages/Dashboard/RecruiterAccountSettings'));
const RecruiterProfile = lazy(() => import('./pages/Dashboard/RecruiterProfile'));

const AccountSettings = lazy(() => import('./pages/Dashboard/AccountSettings'));
const ConnectedRepositories = lazy(() => import('./pages/Dashboard/ConnectedRepositories'));
const AnalysisDetail = lazy(() => import('./pages/AnalysisDetail'));
const ManagerRequirements = lazy(() => import('./pages/Dashboard/ManagerRequirements'));
const DeveloperProfile = lazy(() => import('./pages/Dashboard/DeveloperProfile'));

function App() {
  return (
    <Router>
      <Suspense fallback={<div style={{ padding: 24 }}>Loading...</div>}>
        <Routes>
          {/* ── Auth pages ── */}
          <Route path="/" element={<Register />} />
          <Route path="/login" element={<Login />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          <Route path="/verify-email" element={<VerifyEmail />} />
          <Route path="/auth/github/callback" element={<GitHubCallback />} />
          <Route path="/select-role" element={<RoleSelection />} />

          {/* ── Developer routes ── */}
          <Route path="/dashboard/developer" element={<RepositoryAnalysis />} />
          <Route path="/dashboard/developer/analysis" element={<RepositoryAnalysis />} />

          {/* ── Analysis detail — /analysis/:analysisId ── */}
          <Route path="/analysis/:analysisId" element={<AnalysisDetail />} />

          <Route path="/dashboard/developer/skills" element={<DeveloperSkills />} />
          <Route path="/dashboard/developer/security" element={<DeveloperSecurity />} />
          <Route path="/dashboard/developer/requirements" element={<DeveloperRequirements />} />
          <Route path="/dashboard/developer/learning" element={<DeveloperLearning />} />
          <Route path="/dashboard/developer/profile" element={<DeveloperProfile />} />

          <Route path="/settings/account" element={<AccountSettings />} />
          <Route path="/settings/repositories" element={<ConnectedRepositories />} />

          {/* ── Manager routes ── */}
          <Route path="/dashboard/manager" element={<RepositoryAnalysis />} />
          <Route path="/dashboard/manager/analysis" element={<RepositoryAnalysis />} />
          <Route path="/dashboard/manager/security" element={<ManagerSecurityDashboard />} />
          <Route path="/dashboard/manager/requirements" element={<ManagerRequirements />} />
          <Route path="/dashboard/manager/profile" element={<ManagerProfile />} />
          <Route path="/dashboard/manager/account-settings" element={<ManagerAccountSettings />} />
          <Route path="/dashboard/manager/team" element={<ManagerDashboard />} />

          {/* ── Recruiter routes ── */}
          <Route path="/dashboard/recruiter" element={<RecruiterDashboard />} />
          <Route path="/dashboard/recruiter/analysis" element={<RecruiterDashboard />} />
          <Route path="/dashboard/recruiter/profile" element={<RecruiterProfile />} />
          <Route path="/dashboard/recruiter/account-settings" element={<RecruiterAccountSettings />} />
          <Route path="/dashboard/recruiter/candidates" element={<CandidateEvaluation />} />

          {/* ── Fallback ── */}
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Suspense>
    </Router>
  );
}

export default App;
