import { Navigate, Route, Routes } from "react-router-dom";
import AppShell from "./components/AppShell.jsx";
import GuestRoute from "./components/GuestRoute.jsx";
import ProtectedRoute from "./components/ProtectedRoute.jsx";
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
import DashboardPage from "./pages/DashboardPage.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import MarketsPage from "./pages/MarketsPage.jsx";
import ModulePage from "./pages/ModulePage.jsx";
import RegisterPage from "./pages/RegisterPage.jsx";

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
      <Route element={<PrivateShell />}>
        <Route path="/accueil" element={<DashboardPage />} />
        <Route path="/marches" element={<MarketsPage />} />
        <Route
          path="/trading"
          element={
            <ModulePage
              crumb="TradeLab / Trading"
              title="Trading"
              lead="Passez un ordre et suivez son effet sur le cash et les positions."
            />
          }
        />
        <Route
          path="/portefeuille"
          element={
            <ModulePage
              crumb="TradeLab / Portefeuille"
              title="Portefeuille"
              lead="Le détail des positions et du cash viendra du module trading."
            />
          }
        />
        <Route
          path="/analyse"
          element={
            <ModulePage
              crumb="TradeLab / Analyse"
              title="Analyse"
              lead="Les indicateurs et graphiques avancés seront ajoutés avec le module d'analyse."
            />
          }
        />
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
        <Route
          path="/actuariat"
          element={
            <ModulePage
              crumb="TradeLab / Intelligence"
              title="Actuariat"
              lead="Les calculs actuariels seront ajoutés dans ce module."
            />
          }
        />
        <Route
          path="/formation"
          element={
            <ModulePage
              crumb="TradeLab / Communauté"
              title="Formation"
              lead="Parcours et exercices de la salle de marché."
            />
          }
        />
        <Route
          path="/classement"
          element={
            <ModulePage
              crumb="TradeLab / Communauté"
              title="Classement"
              lead="Comparaison des performances entre traders."
            />
          }
        />
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
