import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import apiClient from "../services/apiClient";
import { useAuth } from "../context/AuthContext";
import { errorMessage } from "../utils/format";
import { downloadCsv, ImportPanel } from "./DataSettings";
import Sheet from "./Sheet";
import { Button } from "./ui";

const IMPORTABLE = ["customers", "products", "deals"];

/** Import and Export for one list page: Export downloads this page's records
 *  as a spreadsheet (CSV, opens in Excel); Import brings rows in from one,
 *  matching its columns first. The same as Settings > Data, one kind at a
 *  time. Admins and managers, like Settings > Data. */
export default function ImportExportButtons({ entity }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [importing, setImporting] = useState(false);
  const exporting = useMutation({
    mutationFn: () => apiClient.get(`/exports/${entity}`, { responseType: "text" }).then((r) => r.data),
    onSuccess: (text) => {
      downloadCsv(`ygt-${entity}-${new Date().toISOString().slice(0, 10)}.csv`, text);
      toast.success(t("importExport.exported", { what: t(`data.exports.${entity}`) }));
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  if (!["admin", "manager"].includes(user?.role)) return null;
  const canImport = IMPORTABLE.includes(entity);

  return (
    <>
      {canImport && (
        <Button variant="secondary" onClick={() => setImporting(true)}>
          <ArrowIcon up /> {t("importExport.import")}
        </Button>
      )}
      <Button variant="secondary" onClick={() => exporting.mutate()} disabled={exporting.isPending}>
        <ArrowIcon /> {exporting.isPending ? t("importExport.exporting") : t("importExport.export")}
      </Button>
      {canImport && (
        <Sheet open={importing} onClose={() => setImporting(false)} title={t("importExport.importTitle", { what: t(`data.exports.${entity}`) })}>
          <ImportPanel entity={entity} />
        </Sheet>
      )}
    </>
  );
}

function ArrowIcon({ up = false }) {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4" aria-hidden="true">
      {up ? <path d="M10 13V3m0 0L6.5 6.5M10 3l3.5 3.5M4 13.5V16a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-2.5" /> : <path d="M10 3v10m0 0-3.5-3.5M10 13l3.5-3.5M4 13.5V16a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-2.5" />}
    </svg>
  );
}
