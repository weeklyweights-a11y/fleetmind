import { NavLink } from "react-router-dom";

const NAV = [
  { to: "/", label: "Fleet", end: true },
  { to: "/trucks", label: "Trucks" },
  { to: "/drivers", label: "Drivers" },
  { to: "/compliance", label: "Compliance" },
  { to: "/financials", label: "Financials" },
  { to: "/vendors", label: "Vendors" },
  { to: "/anomalies", label: "Anomalies" },
  { to: "/documents", label: "Documents" },
  { to: "/review", label: "Review" },
];

export function Sidebar({ open, onClose }) {
  return (
    <>
      {open && (
        <button
          type="button"
          className="fixed inset-0 bg-black/50 z-40 md:hidden"
          onClick={onClose}
          aria-label="Close menu"
        />
      )}
      <aside
        className={`fixed md:static z-50 md:z-auto top-0 left-0 h-full w-56 bg-slate-900 border-r border-slate-800 flex flex-col transform transition-transform ${
          open ? "translate-x-0" : "-translate-x-full md:translate-x-0"
        }`}
      >
        <div className="p-4 border-b border-slate-800">
          <h1 className="text-lg font-bold text-white">FleetMind</h1>
        </div>
        <nav className="flex-1 p-2 space-y-1">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              onClick={onClose}
              className={({ isActive }) =>
                `block px-3 py-2 rounded text-sm ${
                  isActive ? "bg-slate-800 text-white" : "text-slate-400 hover:bg-slate-800/50 hover:text-slate-200"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
    </>
  );
}
