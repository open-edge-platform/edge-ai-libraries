import { Outlet } from "react-router";
import { Toaster } from "@/components/ui/sonner.tsx";

const Layout = () => {
  return (
    <div>
      <Outlet />
      <Toaster position="top-center" richColors />
    </div>
  );
};

export default Layout;
