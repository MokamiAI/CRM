import { Routes, Route } from "react-router-dom";

function Placeholder({ title }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50">
      <div className="text-center">
        <h1 className="text-2xl font-semibold text-gray-800">{title}</h1>
        <p className="mt-2 text-gray-500">
          CRM & Invoice Management System — frontend scaffold (Phase 1)
        </p>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Placeholder title="Dashboard" />} />
    </Routes>
  );
}
