import { AlertCircle, Home } from "lucide-react";
import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <div className="flex min-h-full flex-col items-center justify-center gap-6 py-24 text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gray-800 border border-gray-700">
        <AlertCircle className="h-8 w-8 text-gray-400" />
      </div>
      <div className="space-y-2">
        <h1 className="text-5xl font-bold text-gray-200">404</h1>
        <p className="text-xl font-medium text-gray-300">Page not found</p>
        <p className="text-sm text-gray-500 max-w-xs">
          The page you&apos;re looking for doesn&apos;t exist or has been moved.
        </p>
      </div>
      <Link to="/" className="btn-primary">
        <Home className="h-4 w-4" />
        Back to Dashboard
      </Link>
    </div>
  );
}
