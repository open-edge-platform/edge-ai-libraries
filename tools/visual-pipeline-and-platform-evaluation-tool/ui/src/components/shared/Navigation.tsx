import { NavLink } from "react-router";
import { Home, Film, Cpu, Gauge, Grid3x3, ListTodo } from "lucide-react";

const Navigation = () => {
  const navItems = [
    { to: "/", label: "Pipelines", icon: Home },
    { to: "/models", label: "Models", icon: Cpu },
    { to: "/videos", label: "Videos", icon: Film },
    { to: "/tests/performance", label: "Performance", icon: Gauge },
    { to: "/tests/density", label: "Density", icon: Grid3x3 },
    { to: "/jobs", label: "Jobs", icon: ListTodo },
  ];

  return (
    <nav className="bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800">
      <div className="flex items-center gap-1 px-4">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-2 px-4 py-3 text-sm font-medium transition-colors ${
                isActive
                  ? "text-blue-600 dark:text-blue-400 border-b-2 border-blue-600 dark:border-blue-400"
                  : "text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 border-b-2 border-transparent"
              }`
            }
          >
            <item.icon className="w-4 h-4" />
            {item.label}
          </NavLink>
        ))}
      </div>
    </nav>
  );
};

export default Navigation;
