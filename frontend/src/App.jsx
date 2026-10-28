import { Navigate, Route, Routes } from "react-router-dom";
import AppShell from "./components/AppShell.jsx";
import GuestRoute from "./components/GuestRoute.jsx";
import ProtectedRoute from "./components/ProtectedRoute.jsx";
import AnalysisPage from "./pages/AnalysisPage.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import MarketsPage from "./pages/MarketsPage.jsx";
import ModulePage from "./pages/ModulePage.jsx";
import PortfolioPage from "./pages/PortfolioPage.jsx";
import RegisterPage from "./pages/RegisterPage.jsx";
import TradingPage from "./pages/TradingPage.jsx";

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
        <Route
          path="/administration"
          element={
            <ModulePage
              crumb="TradeLab / Communauté"
              title="Administration"
              lead="Gestion des comptes et des rôles."
            />
          }
        />
      </Route>
    </Routes>
  );
}
