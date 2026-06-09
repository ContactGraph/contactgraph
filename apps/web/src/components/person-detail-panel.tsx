"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import type { PersonDetailResult, UpdatePersonRequest } from "@/lib/api-types";
import { formatDate, formatSourceType } from "@/lib/formatters";
import { proxyPost } from "@/lib/proxy-client";

interface PersonFormState {
  first_name: string;
  last_name: string;
  primary_email: string;
  phone: string;
  org_name: string;
  current_role: string;
  location: string;
  linkedin_url: string;
  bio_summary: string;
}

function personToForm(person: PersonDetailResult): PersonFormState {
  return {
    first_name: person.first_name,
    last_name: person.last_name,
    primary_email: person.primary_email ?? "",
    phone: person.phone ?? "",
    org_name: person.org_name ?? "",
    current_role: person.current_role ?? "",
    location: person.location ?? "",
    linkedin_url: person.social_profiles.linkedin ?? "",
    bio_summary: person.bio_summary ?? "",
  };
}

function ReadOnlyField({
  label,
  value,
}: {
  label: string;
  value: string | null | undefined;
}) {
  if (!value) {
    return null;
  }
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </dt>
      <dd className="mt-1 text-sm">{value}</dd>
    </div>
  );
}

export function PersonDetailPanel({ person }: { person: PersonDetailResult }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<PersonFormState>(() => personToForm(person));
  const [saved, setSaved] = useState<boolean>(false);

  const saveMutation = useMutation({
    mutationFn: (payload: UpdatePersonRequest) =>
      proxyPost<PersonDetailResult>("update-person", payload),
    onSuccess: async (updated: PersonDetailResult) => {
      setForm(personToForm(updated));
      setSaved(true);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["person", person.person_id] }),
        queryClient.invalidateQueries({ queryKey: ["people"] }),
      ]);
      window.setTimeout(() => setSaved(false), 2500);
    },
  });

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    const payload: UpdatePersonRequest = {
      person_id: person.person_id,
      first_name: form.first_name,
      last_name: form.last_name,
      primary_email: form.primary_email,
      phone: form.phone,
      org_name: form.org_name,
      current_role: form.current_role,
      location: form.location,
      linkedin_url: form.linkedin_url,
      bio_summary: form.bio_summary,
    };
    saveMutation.mutate(payload);
  };

  return (
    <div className="flex-1 space-y-6 overflow-y-auto px-6 py-4">
      <div className="space-y-2">
        <div className="flex flex-wrap gap-2">
          {person.is_human ? <Badge variant="success">Human</Badge> : null}
          {person.is_broadcast ? <Badge variant="warning">Broadcast</Badge> : null}
          {person.is_automated ? <Badge variant="secondary">Automated</Badge> : null}
        </div>
        <p className="text-sm text-muted-foreground">{person.message}</p>
      </div>

      <form className="space-y-4" onSubmit={handleSubmit}>
        <h3 className="text-sm font-medium">Edit contact</h3>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="person-first-name">First name</Label>
            <Input
              id="person-first-name"
              value={form.first_name}
              onChange={(event) =>
                setForm((current) => ({ ...current, first_name: event.target.value }))
              }
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="person-last-name">Last name</Label>
            <Input
              id="person-last-name"
              value={form.last_name}
              onChange={(event) =>
                setForm((current) => ({ ...current, last_name: event.target.value }))
              }
            />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="person-email">Primary email</Label>
          <Input
            id="person-email"
            type="email"
            value={form.primary_email}
            onChange={(event) =>
              setForm((current) => ({ ...current, primary_email: event.target.value }))
            }
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="person-phone">Phone</Label>
          <Input
            id="person-phone"
            value={form.phone}
            onChange={(event) =>
              setForm((current) => ({ ...current, phone: event.target.value }))
            }
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="person-org">Organization</Label>
          <Input
            id="person-org"
            value={form.org_name}
            onChange={(event) =>
              setForm((current) => ({ ...current, org_name: event.target.value }))
            }
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="person-role">Role</Label>
          <Input
            id="person-role"
            value={form.current_role}
            onChange={(event) =>
              setForm((current) => ({ ...current, current_role: event.target.value }))
            }
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="person-location">Location</Label>
          <Input
            id="person-location"
            value={form.location}
            onChange={(event) =>
              setForm((current) => ({ ...current, location: event.target.value }))
            }
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="person-linkedin">LinkedIn URL</Label>
          <Input
            id="person-linkedin"
            value={form.linkedin_url}
            onChange={(event) =>
              setForm((current) => ({ ...current, linkedin_url: event.target.value }))
            }
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="person-bio">Bio</Label>
          <Textarea
            id="person-bio"
            rows={3}
            value={form.bio_summary}
            onChange={(event) =>
              setForm((current) => ({ ...current, bio_summary: event.target.value }))
            }
          />
        </div>
        {saveMutation.error ? (
          <Alert variant="destructive">
            <AlertDescription>{saveMutation.error.message}</AlertDescription>
          </Alert>
        ) : null}
        <div className="flex items-center gap-2">
          <Button type="submit" size="sm" disabled={saveMutation.isPending}>
            {saveMutation.isPending ? <Loader2 className="animate-spin" /> : null}
            Save changes
          </Button>
          {saved ? (
            <span className="text-xs text-muted-foreground">Saved</span>
          ) : null}
        </div>
      </form>

      <Separator />

      <dl className="grid gap-4">
        <ReadOnlyField
          label="First contact"
          value={formatDate(person.first_contact_at)}
        />
        <ReadOnlyField
          label="Last contact"
          value={formatDate(person.last_contact_at)}
        />
        <ReadOnlyField
          label="Last genuine interaction"
          value={formatDate(person.last_genuine_interaction_at)}
        />
        <ReadOnlyField
          label="Tie strength"
          value={person.tie_strength_score.toFixed(2)}
        />
        <ReadOnlyField
          label="Email count"
          value={person.email_count.toString()}
        />
      </dl>

      {person.emails.length > 0 ? (
        <section className="space-y-2">
          <h3 className="text-sm font-medium">Emails</h3>
          <ul className="space-y-1 text-sm">
            {person.emails.map((email: string) => (
              <li key={email}>{email}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {person.sources.length > 0 ? (
        <section className="space-y-2">
          <h3 className="text-sm font-medium">Sources</h3>
          <div className="flex flex-wrap gap-2">
            {person.sources.map((source: string) => (
              <Badge key={source} variant="outline">
                {formatSourceType(source)}
              </Badge>
            ))}
          </div>
        </section>
      ) : null}

      {Object.keys(person.social_profiles).length > 0 ? (
        <section className="space-y-2">
          <h3 className="text-sm font-medium">Web links</h3>
          <ul className="space-y-2 text-sm">
            {Object.entries(person.social_profiles).map(([platform, url]) => (
              <li key={platform}>
                <span className="font-medium capitalize">{platform}: </span>
                <a
                  href={url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-primary underline-offset-4 hover:underline"
                >
                  {url}
                </a>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {person.inferred_categories.length > 0 ? (
        <section className="space-y-2">
          <h3 className="text-sm font-medium">Categories</h3>
          <div className="flex flex-wrap gap-2">
            {person.inferred_categories.map((category: string) => (
              <Badge key={category} variant="secondary">
                {category}
              </Badge>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
