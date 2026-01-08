import { NavLink, useLocation, useNavigate, useParams } from "react-router";
import {
  ArrowLeft,
  Cpu,
  Film,
  Gauge,
  Grid3x3,
  Home,
  ListTodo,
  Moon,
  Sun,
} from "lucide-react";
import logo from "@/assets/digital-unboxed-energyblue-white.svg";
import { PipelineNameEdit } from "@/components/shared/PipelineNameEdit.tsx";
import { useTheme } from "next-themes";

const Navigation = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const params = useParams();
  const { theme, setTheme } = useTheme();

  // Check if we're on the pipeline editor page
  const isPipelineEditorPage = location.pathname.startsWith("/pipelines/");
  const pipelineId = params.id;

  const navItems = [
    { to: "/", label: "Pipelines", icon: Home },
    { to: "/models", label: "Models", icon: Cpu },
    { to: "/videos", label: "Videos", icon: Film },
    { to: "/tests/performance", label: "Performance", icon: Gauge },
    { to: "/tests/density", label: "Density", icon: Grid3x3 },
    { to: "/jobs", label: "Jobs", icon: ListTodo },
  ];

  if (isPipelineEditorPage && pipelineId) {
    return (
      <nav className="bg-white dark:bg-[#313236] border-b border-gray-200 dark:border-gray-800">
        <div className="flex items-center justify-between px-4 h-[60px]">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate("/")}
              className="flex items-center gap-2 text-gray-700 dark:text-gray-300 hover:text-classic-blue dark:hover:text-energy-blue transition-colors cursor-pointer"
            >
              <ArrowLeft className="w-5 h-5" />
              <span className="text-sm font-medium">Back</span>
            </button>
            <div className="h-7 w-px bg-gray-300 dark:bg-gray-700" />
            <span className="text-gray-900 dark:text-white font-medium text-lg">
              <PipelineNameEdit pipelineId={pipelineId} />
            </span>
          </div>
          <button
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            aria-label="Toggle theme"
          >
            {theme === "dark" ? (
              <Sun className="w-5 h-5 text-white hover:text-energy-blue" />
            ) : (
              <Moon className="w-5 h-5 hover:text-cyan-300 text-gray-700" />
            )}
          </button>
        </div>
      </nav>
    );
  }

  return (
    <nav className="bg-classic-blue dark:bg-[#313236] border-b border-gray-200 dark:border-gray-800">
      <div className="flex items-center justify-between px-4 h-[60px]">
        <div className="flex items-center gap-6">
          <img src={logo} alt="Intel" className="h-7" />
          <span className="text-white font-medium text-lg pt-1.5">ViPPET</span>
          <div className="flex items-center gap-1">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  `flex items-center gap-2 px-4 pt-5 pb-3 text-md font-medium transition-colors ${
                    isActive
                      ? "text-white border-b-2 border-white dark:border-blue-400 dark:hover:bg-[#242528] hover:bg-classic-blue-hover"
                      : "text-white dark:text-[#ffffff] dark:hover:bg-[#242528] border-b-2 border-transparent hover:bg-classic-blue-hover"
                  }`
                }
              >
                <item.icon className="w-4 h-4" />
                {item.label}
              </NavLink>
            ))}
          </div>
        </div>
        <button
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          aria-label="Toggle theme"
        >
          {theme === "dark" ? (
            <Sun className="w-5 h-5 text-white hover:text-energy-blue" />
          ) : (
            <Moon className="w-5 h-5 text-white hover:text-cyan-300" />
          )}
        </button>
      </div>
    </nav>
  );
};

export default Navigation;
