import { createContext, useCallback, useContext, useEffect, useMemo, useRef } from "react";
import { useLocation } from "react-router-dom";

const DashboardContext = createContext(null);

const ROUTE_PANELS = {
  "/compliance": ["compliance"],
  "/financials": ["financials"],
  "/": ["overview"],
};

export function DashboardContextProvider({ children }) {
  const location = useLocation();
  const pageRef = useRef({ current_entity: null, visible_panels: [] });

  const setPageContext = useCallback((ctx) => {
    pageRef.current = ctx || { current_entity: null, visible_panels: [] };
  }, []);

  const getContext = useCallback(() => {
    const path = location.pathname;
    const truckMatch = path.match(/^\/trucks\/(\d+)/);
    const driverMatch = path.match(/^\/drivers\/([^/]+)/);
    const vendorMatch = path.match(/^\/vendors\/([^/]+)/);

    let current_entity = pageRef.current.current_entity;
    if (!current_entity) {
      if (truckMatch) {
        current_entity = { type: "truck", unit: Number(truckMatch[1]) };
      } else if (driverMatch) {
        current_entity = { type: "driver", id: driverMatch[1] };
      } else if (vendorMatch) {
        current_entity = { type: "vendor", id: vendorMatch[1] };
      }
    }

    const base = "/" + (path.split("/").filter(Boolean)[0] || "");
    const visible_panels =
      pageRef.current.visible_panels?.length > 0
        ? pageRef.current.visible_panels
        : ROUTE_PANELS[base] ||
          (truckMatch ? ["identity", "maintenance", "compliance", "financials"] : []);

    return {
      current_page: path,
      current_entity,
      visible_panels,
    };
  }, [location.pathname]);

  const value = useMemo(() => ({ setPageContext, getContext }), [setPageContext, getContext]);

  return <DashboardContext.Provider value={value}>{children}</DashboardContext.Provider>;
}

export function useDashboardContext() {
  return useContext(DashboardContext);
}

export function usePageDashboardContext(ctx) {
  const dash = useDashboardContext();
  useEffect(() => {
    dash?.setPageContext?.(ctx);
  }, [ctx, dash]);
}
