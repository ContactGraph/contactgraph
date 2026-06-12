"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import Link from "next/link";
import { forwardRef, useEffect, useImperativeHandle, useMemo, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import type { OrgDetailResult, UpdateOrgRequest } from "@/lib/api-types";
import { formatCompanySize } from "@/lib/company-size";
import { isRecordFormDirty } from "@/lib/detail-form-dirty";
import type { EditableDetailPanelHandle } from "@/lib/editable-detail-panel";
import { proxyPost } from "@/lib/proxy-client";

interface OrgFormState {
  name: string;
  primary_domain: string;
  description: string;
  linkedin_url: string;
  careers_url: string;
  categories: string;
}

function orgToForm(org: OrgDetailResult): OrgFormState {
  return {
    name: org.name,
    primary_domain: org.primary_domain ?? "",
    description: org.description ?? "",
    linkedin_url: org.linkedin_url ?? "",
    careers_url: org.careers_url ?? "",
    categories: org.categories.join(", "),
  };
}

function parseCategories(raw: string): string[] {
  return raw
    .split(",")
    .map((category: string) => category.trim())
    .filter(Boolean);
}

function buildUpdatePayload(orgId: string, form: OrgFormState): UpdateOrgRequest {
  return {
    org_id: orgId,
    name: form.name,
    primary_domain: form.primary_domain,
    description: form.description,
    linkedin_url: form.linkedin_url,
    careers_url: form.careers_url,
    categories: parseCategories(form.categories),
  };
}

export const OrgDetailPanel = forwardRef<
  EditableDetailPanelHandle,
  {
    org: OrgDetailResult;
    onDirtyChange?: (isDirty: boolean) => void;
  }
>(function OrgDetailPanel({ org, onDirtyChange }, ref) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<OrgFormState>(() => orgToForm(org));
  const [saved, setSaved] = useState<boolean>(false);
  const baseline: OrgFormState = useMemo(() => orgToForm(org), [org]);
  const isDirty: boolean = useMemo(
    () => isRecordFormDirty(form, baseline),
    [form, baseline],
  );

  useEffect(() => {
    onDirtyChange?.(isDirty);
  }, [isDirty, onDirtyChange]);

  const saveMutation = useMutation({
    mutationFn: (payload: UpdateOrgRequest) =>
      proxyPost<OrgDetailResult>("update-org", payload),
    onSuccess: async (updated: OrgDetailResult) => {
      setForm(orgToForm(updated));
      setSaved(true);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["organization", org.org_id] }),
        queryClient.invalidateQueries({ queryKey: ["organizations"] }),
      ]);
      window.setTimeout(() => setSaved(false), 2500);
    },
  });

  useImperativeHandle(
    ref,
    () => ({
      save: async (): Promise<boolean> => {
        if (!isDirty) {
          return true;
        }
        try {
          await saveMutation.mutateAsync(buildUpdatePayload(org.org_id, form));
          return true;
        } catch {
          return false;
        }
      },
    }),
    [form, isDirty, org.org_id, saveMutation],
  );

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    saveMutation.mutate(buildUpdatePayload(org.org_id, form));
  };

  return (
    <div className="flex-1 space-y-6 overflow-y-auto px-6 py-4">
      <p className="text-sm text-muted-foreground">{org.message}</p>

      <form className="space-y-4" onSubmit={handleSubmit}>
        <h3 className="text-sm font-medium">Edit organization</h3>
        <div className="space-y-1.5">
          <Label htmlFor="org-name">Name</Label>
          <Input
            id="org-name"
            value={form.name}
            onChange={(event) =>
              setForm((current) => ({ ...current, name: event.target.value }))
            }
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="org-domain">Domain</Label>
          <Input
            id="org-domain"
            value={form.primary_domain}
            onChange={(event) =>
              setForm((current) => ({ ...current, primary_domain: event.target.value }))
            }
            placeholder="example.com"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="org-description">Description</Label>
          <Textarea
            id="org-description"
            rows={3}
            value={form.description}
            onChange={(event) =>
              setForm((current) => ({ ...current, description: event.target.value }))
            }
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="org-linkedin">LinkedIn URL</Label>
          <Input
            id="org-linkedin"
            value={form.linkedin_url}
            onChange={(event) =>
              setForm((current) => ({ ...current, linkedin_url: event.target.value }))
            }
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="org-careers">Careers URL</Label>
          <Input
            id="org-careers"
            value={form.careers_url}
            onChange={(event) =>
              setForm((current) => ({ ...current, careers_url: event.target.value }))
            }
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="org-categories">Categories</Label>
          <Input
            id="org-categories"
            value={form.categories}
            onChange={(event) =>
              setForm((current) => ({ ...current, categories: event.target.value }))
            }
            placeholder="naics:51, venture_capital"
          />
        </div>
        {saveMutation.error ? (
          <Alert variant="destructive">
            <AlertDescription>{saveMutation.error.message}</AlertDescription>
          </Alert>
        ) : null}
        <div className="flex items-center gap-2">
          <Button
            type="submit"
            size="sm"
            disabled={!isDirty || saveMutation.isPending}
          >
            {saveMutation.isPending ? <Loader2 className="animate-spin" /> : null}
            Save changes
          </Button>
          {saved ? (
            <span className="text-xs text-muted-foreground">Saved</span>
          ) : null}
        </div>
      </form>

      <dl className="grid gap-4 sm:grid-cols-2">
        <div>
          <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Size
          </dt>
          <dd className="mt-1 text-sm">
            {formatCompanySize(org.company_size_band, org.employee_count)}
          </dd>
        </div>
        <div>
          <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Contacts
          </dt>
          <dd className="mt-1 text-sm">{org.contact_count.toString()}</dd>
        </div>
      </dl>

      {org.aliases.length > 0 ? (
        <section className="space-y-2">
          <h3 className="text-sm font-medium">Aliases</h3>
          <ul className="space-y-1 text-sm">
            {org.aliases.map((alias: string) => (
              <li key={alias}>{alias}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <Separator />

      <section className="space-y-3">
        <h3 className="text-sm font-medium">People at this organization</h3>
        {org.people.length === 0 ? (
          <p className="text-sm text-muted-foreground">No contacts linked yet.</p>
        ) : (
          <ul className="divide-y rounded-md border">
            {org.people.map((person) => (
              <li key={person.person_id} className="px-3 py-2 text-sm">
                <Link
                  href={`/graph?tab=people&person=${encodeURIComponent(person.person_id)}`}
                  className="font-medium text-primary hover:underline"
                >
                  {person.display_name}
                </Link>
                <p className="text-muted-foreground">
                  {[person.current_role, person.primary_email]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
});
