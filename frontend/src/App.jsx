import { BrowserRouter, Routes, Route } from "react-router-dom";
import { WebSocketProvider } from "./context/WebSocketContext.jsx";
import { AppShell } from "./components/layout/AppShell.jsx";
import FleetOverview from "./pages/FleetOverview.jsx";
import TruckList from "./pages/TruckList.jsx";
import TruckDetail from "./pages/TruckDetail.jsx";
import DriverList from "./pages/DriverList.jsx";
import DriverDetail from "./pages/DriverDetail.jsx";
import ComplianceMatrix from "./pages/ComplianceMatrix.jsx";
import FinancialAnalytics from "./pages/FinancialAnalytics.jsx";
import VendorList from "./pages/VendorList.jsx";
import VendorDetail from "./pages/VendorDetail.jsx";
import DocumentList from "./pages/DocumentList.jsx";
import DocumentViewer from "./pages/DocumentViewer.jsx";
import ReviewQueue from "./pages/ReviewQueue.jsx";
import AnomalyFeed from "./pages/AnomalyFeed.jsx";
import AdminHealth from "./pages/AdminHealth.jsx";

export default function App() {
  return (
    <WebSocketProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<FleetOverview />} />
            <Route path="trucks" element={<TruckList />} />
            <Route path="trucks/:id" element={<TruckDetail />} />
            <Route path="drivers" element={<DriverList />} />
            <Route path="drivers/:id" element={<DriverDetail />} />
            <Route path="compliance" element={<ComplianceMatrix />} />
            <Route path="financials" element={<FinancialAnalytics />} />
            <Route path="vendors" element={<VendorList />} />
            <Route path="vendors/:id" element={<VendorDetail />} />
            <Route path="anomalies" element={<AnomalyFeed />} />
            <Route path="admin/health" element={<AdminHealth />} />
            <Route path="documents" element={<DocumentList />} />
            <Route path="documents/:id" element={<DocumentViewer />} />
            <Route path="review" element={<ReviewQueue />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </WebSocketProvider>
  );
}
