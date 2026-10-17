"use client";

import { useState } from "react";

import { ConsentText } from "@/components/account/ConsentNotice";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardCaption, CardTitle } from "@/components/ui/Card";
import { Dialog } from "@/components/ui/Dialog";
import { TextField } from "@/components/ui/fields";
import { PageHeader } from "@/components/ui/PageHeader";
import { ErrorState, Skeleton } from "@/components/ui/States";
import { useConsent, useDeleteData, useExportData } from "@/lib/api/topic";
import { formatDate } from "@/lib/format";

const PHRASE = "delete my data";

export function AccountScreen() {
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader
        title="Your data"
        intro="What PaySense keeps, and your right to take it with you or delete it (PDPA)."
      />
      <Notice />
      <Export />
      <Delete />
    </div>
  );
}

function Notice() {
  const consent = useConsent();
  return (
    <Card>
      <CardTitle>The privacy and assistant notice</CardTitle>
      {consent.isPending ? (
        <Skeleton lines={4} label="Loading the notice" />
      ) : consent.isError ? (
        <ErrorState message={consent.error.message} onRetry={() => consent.refetch()} />
      ) : (
        <>
          <CardCaption>
            {consent.data.accepted && consent.data.accepted_at
              ? `You accepted version ${consent.data.version} on ${formatDate(consent.data.accepted_at.slice(0, 10))}.`
              : `Version ${consent.data.version}, not yet accepted.`}
          </CardCaption>
          <div className="mt-4">
            <ConsentText consent={consent.data} />
          </div>
        </>
      )}
    </Card>
  );
}

function Export() {
  const exporter = useExportData();
  return (
    <Card>
      <CardTitle>Download your data</CardTitle>
      <CardCaption>
        Everything PaySense holds about you, as one JSON file: transactions, plans, budgets, saved
        risk reports and the log of what the assistant did. Your passphrase is never included.
      </CardCaption>
      <div className="mt-3">
        <Button
          variant="secondary"
          disabled={exporter.isPending}
          onClick={() =>
            exporter.mutate(undefined, {
              onSuccess: (data) => {
                const blob = new Blob([JSON.stringify(data, null, 2)], {
                  type: "application/json",
                });
                const url = URL.createObjectURL(blob);
                const link = document.createElement("a");
                link.href = url;
                link.download = "paysense-my-data.json";
                link.click();
                URL.revokeObjectURL(url);
              },
            })
          }
        >
          {exporter.isPending ? "Preparing…" : "Download my data"}
        </Button>
      </div>
      {exporter.isSuccess && (
        <p role="status" className="mt-2 text-[12px] text-success">
          Your file is ready.
        </p>
      )}
      {exporter.isError && (
        <p role="alert" className="mt-2 text-[12px] text-danger">
          {exporter.error.message}
        </p>
      )}
    </Card>
  );
}

function Delete() {
  const [open, setOpen] = useState(false);
  const [phrase, setPhrase] = useState("");
  const [passphrase, setPassphrase] = useState("");
  const remove = useDeleteData();
  const close = () => {
    setOpen(false);
    setPhrase("");
    setPassphrase("");
  };
  return (
    <Card>
      <CardTitle>Delete your data</CardTitle>
      <CardCaption>
        Removes every transaction, plan, budget, report and assistant record you have. Your account
        stays, empty, so you can start again. This cannot be undone.
      </CardCaption>
      {remove.isSuccess ? (
        <div className="mt-3">
          <Banner tone="success" title="Your data has been deleted" />
        </div>
      ) : (
        <div className="mt-3">
          <Button variant="danger" onClick={() => setOpen(true)}>
            Delete my data…
          </Button>
        </div>
      )}
      <Dialog
        open={open}
        title="Delete all your data?"
        onClose={close}
        dismissible={!remove.isPending}
      >
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (phrase.trim().toLowerCase() !== PHRASE || !passphrase) return;
            remove.mutate(passphrase, { onSuccess: close });
          }}
        >
          <TextField
            label={`Type "${PHRASE}" to confirm`}
            value={phrase}
            onChange={(event) => setPhrase(event.target.value)}
            autoComplete="off"
            data-autofocus
          />
          <TextField
            label="Your passphrase"
            type="password"
            value={passphrase}
            onChange={(event) => setPassphrase(event.target.value)}
            autoComplete="current-password"
          />
          {remove.isError && (
            <p role="alert" className="text-[12px] text-danger">
              {remove.error.message}
            </p>
          )}
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="secondary" onClick={close}>
              Keep my data
            </Button>
            <Button
              type="submit"
              variant="danger"
              disabled={phrase.trim().toLowerCase() !== PHRASE || !passphrase || remove.isPending}
            >
              {remove.isPending ? "Deleting…" : "Delete everything"}
            </Button>
          </div>
        </form>
      </Dialog>
    </Card>
  );
}
