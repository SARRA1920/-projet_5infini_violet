import { lazy } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import AppShell from "./components/AppShell.jsx";
import GuestRoute from "./components/GuestRoute.jsx";
import ProtectedRoute from "./components/ProtectedRoute.jsx";
import ActuarialLayout from "./pages/actuariat/ActuarialLayout.jsx";
import AdminLayout from "./pages/admin/AdminLayout.jsx";
import {
  AdminAudit,
  AdminDashboard,
  AdminFormation,
  AdminMarkets,
  AdminModels,
  AdminResults,
  AdminScenarios,
  AdminSettings,
  AdminUsers,
} from "./pages/admin/AdminPages.jsx";
import AnalysisPage from "./pages/AnalysisPage.jsx";
import ClassementPage from "./pages/ClassementPage.jsx";
import RoomPage from "./pages/RoomPage.jsx";
import RoomsPage from "./pages/RoomsPage.jsx";
import PlacementPage from "./pages/PlacementPage.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import MarketsPage from "./pages/MarketsPage.jsx";
import ModulePage from "./pages/ModulePage.jsx";
import PortfolioPage from "./pages/PortfolioPage.jsx";
import RegisterPage from "./pages/RegisterPage.jsx";
import TradingPage from "./pages/TradingPage.jsx";

// Module Actuariat chargé à la demande : recharts n'alourdit pas les autres écrans.
// Le Suspense est dans ActuarialLayout.
const ActuarialDashboard = lazy(() => import("./pages/actuariat/ActuarialDashboard.jsx"));
const RiskAnalyticsPage = lazy(() => import("./pages/actuariat/RiskAnalyticsPage.jsx"));
const StochasticPage = lazy(() => import("./pages/actuariat/StochasticPage.jsx"));
const FixedIncomePage = lazy(() => import("./pages/actuariat/FixedIncomePage.jsx"));
const OptimizationPage = lazy(() => import("./pages/actuariat/OptimizationPage.jsx"));
const LossModelingPage = lazy(() => import("./pages/actuariat/LossModelingPage.jsx"));
const ModelLabPage = lazy(() => import("./pages/actuariat/ModelLabPage.jsx"));

function PrivateShell() {
  return (
    <ProtectedRoute>
      <AppShell />
    </ProtectedRoute>
  );
}

export default function App() {
  return (
    <Routes>
      <Route
        path="/login"
        element={
          <GuestRoute>
            <LoginPage />
          </GuestRoute>
        }
      />
      <Route
        path="/register"
        element={
          <GuestRoute>
            <RegisterPage />
          </GuestRoute>
        }
      />
      <Route path="/" element={<Navigate to="/login" replace />} />
      <Route
        path="/formation/niveau"
        element={
          <ProtectedRoute>
            <PlacementPage />
          </ProtectedRoute>
        }
      />
      <Route element={<PrivateShell />}>
        <Route path="/accueil" element={<DashboardPage />} />
        <Route path="/marches" element={<MarketsPage />} />
        <Route path="/trading" element={<TradingPage />} />
        <Route path="/portefeuille" element={<PortfolioPage />} />
        <Route path="/analyse" element={<AnalysisPage />} />
        <Route
          path="/ia"
          element={
            <ModulePage
              crumb="TradeLab / Intelligence"
              title="IA & Prédictions"
              lead="Prédiction, agent de trading et analyse de sentiment."
            />
          }
        />
        <Route
          path="/stress-testing"
          element={
            <ModulePage
              crumb="TradeLab / Intelligence"
              title="Stress Testing"
              lead="Scénarios de stress sur les banques synthétiques."
            />
          }
        />
        <Route path="/actuariat" element={<ActuarialLayout />}>
          <Route index element={<ActuarialDashboard />} />
          <Route path="risque" element={<RiskAnalyticsPage />} />
          <Route path="stochastique" element={<StochasticPage />} />
          <Route path="obligations" element={<FixedIncomePage />} />
          <Route path="optimisation" element={<OptimizationPage />} />
          <Route path="pertes" element={<LossModelingPage />} />
          <Route path="laboratoire" element={<ModelLabPage />} />
        </Route>
        <Route path="/formation" element={<RoomsPage />} />
        <Route path="/formation/salle/:runId" element={<RoomPage />} />
        <Route path="/classement" element={<ClassementPage />} />
        <Route path="/administration" element={<AdminLayout />}>
          <Route index element={<AdminDashboard />} />
          <Route path="utilisateurs" element={<AdminUsers />} />
          <Route path="marches" element={<AdminMarkets />} />
          <Route path="formation" element={<AdminFormation />} />
          <Route path="scenarios" element={<AdminScenarios />} />
          <Route path="parametres" element={<AdminSettings />} />
          <Route path="modeles" element={<AdminModels />} />
          <Route path="resultats" element={<AdminResults />} />
          <Route path="audit" element={<AdminAudit />} />
        </Route>
      </Route>
    </Routes>
  );
}
